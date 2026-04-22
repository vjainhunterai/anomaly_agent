"""FastAPI entry point for the Anomaly Agent.

Route groups:
  /api/agent      — step-based conversational agent
  /api/status     — processing status summary + Q&A
  /api/analysis   — analyst panel (setup, Q&A with SQL)
  /api/reports    — reconciliation report, audit trail
  /api/health     — liveness probe
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import airflow_trigger
import database
import llm_service
from session_manager import (
    STEP_AWAIT_DATES,
    STEP_CONFIRM,
    STEP_DONE,
    STEP_ERROR,
    STEP_GREET,
    STEP_PROCESSING,
    Session,
    store,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s :: %(message)s",
)
log = logging.getLogger("anomaly_agent")

app = FastAPI(title="Anomaly Agent", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class StartResponse(BaseModel):
    session_id: str
    step: str
    message: str


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    session_id: str
    step: str
    message: str
    start_date: str | None = None
    end_date: str | None = None
    airflow_run_id: str | None = None


class StatusSummary(BaseModel):
    total_records: int
    anomalies_detected: int
    processing_state: str  # "idle" | "pending" | "running" | "complete" | "error"
    start_date: str | None = None
    end_date: str | None = None
    last_updated: str


class ContractRow(BaseModel):
    id: Any
    status: str
    fields: dict[str, Any]


class StatusAskRequest(BaseModel):
    question: str


class StatusAskResponse(BaseModel):
    answer: str


class Delivery(BaseModel):
    id: str
    label: str
    start_date: str | None = None
    end_date: str | None = None


class AnalysisSetupRequest(BaseModel):
    session_id: str | None = None
    delivery_id: str
    start_date: str | None = None
    end_date: str | None = None


class AnalysisSetupResponse(BaseModel):
    session_id: str
    understanding: str
    anomalies: list[dict[str, Any]]
    final_output: str
    column_info: str
    delivery: Delivery


class AnalysisAskRequest(BaseModel):
    session_id: str
    question: str


class AnalysisAskResponse(BaseModel):
    answer: str
    sql: str | None = None
    rows: list[dict[str, Any]] | None = None


class ReconciliationRequest(BaseModel):
    session_id: str


class ReconciliationResponse(BaseModel):
    report: str
    summary: StatusSummary


class AuditEntry(BaseModel):
    session_id: str
    ts: float
    event: str
    detail: dict[str, Any]


# ---------------------------------------------------------------------------
# Agent step machine helpers
# ---------------------------------------------------------------------------
GREETING = (
    "Hello — welcome to the **Anomaly Detection Agent**. "
    "Please provide a date range (e.g. `2024-12-25 to 2025-12-25`) or type `exit` to quit."
)


def _is_exit(msg: str) -> bool:
    return msg.strip().lower() in {"exit", "quit", "cancel"}


def _handle_await_dates(sess: Session, user_msg: str) -> str:
    parsed = llm_service.normalize_date_range(user_msg)
    ok, reason = llm_service.validate_date_range(parsed["start_date"], parsed["end_date"])
    if not ok:
        sess.step = STEP_AWAIT_DATES
        return (
            f"I couldn't read that date range ({reason}). "
            f"Please try again, e.g. `2024-01-01 to 2024-12-31`."
        )
    sess.start_date = parsed["start_date"]
    sess.end_date = parsed["end_date"]
    sess.step = STEP_CONFIRM
    sess.log("dates_parsed", parsed)
    return (
        f"I parsed:\n\n- **Start date:** `{sess.start_date}`\n"
        f"- **End date:** `{sess.end_date}`\n\n"
        f"Reply `confirm` to run the anomaly pipeline or send a new range."
    )


def _handle_confirm(sess: Session, user_msg: str) -> str:
    low = user_msg.strip().lower()
    if low in {"confirm", "yes", "y", "ok", "go", "run"}:
        return _trigger_pipeline(sess)
    # treat anything else as a new date attempt
    sess.step = STEP_AWAIT_DATES
    return _handle_await_dates(sess, user_msg)


def _trigger_pipeline(sess: Session) -> str:
    sess.step = STEP_PROCESSING
    try:
        database.upsert_anomaly_metadata(sess.start_date, sess.end_date)
        sess.log("metadata_written", {"start": sess.start_date, "end": sess.end_date})
    except Exception as exc:
        sess.step = STEP_ERROR
        sess.last_error = f"Failed to write metadata table: {exc}"
        log.exception("metadata write failed")
        return f"❌ Could not update `anomaly_metadata` table: `{exc}`"

    run_id = f"anomaly_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    sess.airflow_run_id = run_id
    result = airflow_trigger.trigger_airflow_dag(run_id)
    sess.airflow_status = "triggered" if result.ok else "failed"
    sess.log("airflow_trigger", {"ok": result.ok, "run_id": run_id, "stderr": result.stderr})

    if result.ok:
        sess.step = STEP_DONE
        return (
            f"✅ Anomaly pipeline triggered.\n\n"
            f"- **Run ID:** `{run_id}`\n"
            f"- **Range:** `{sess.start_date}` → `{sess.end_date}`\n\n"
            f"Watch the **Status Monitor** panel for progress."
        )
    sess.step = STEP_ERROR
    sess.last_error = result.stderr or "unknown SSH error"
    return (
        f"⚠️ Metadata was written but the Airflow trigger failed:\n\n"
        f"```\n{result.stderr}\n```\n\n"
        f"Fix the SSH / DAG configuration and reply `retry`."
    )


# ---------------------------------------------------------------------------
# /api/agent
# ---------------------------------------------------------------------------
@app.post("/api/agent/start", response_model=StartResponse)
def agent_start() -> StartResponse:
    sess = store.create()
    sess.step = STEP_AWAIT_DATES
    sess.add_turn("assistant", GREETING)
    sess.log("session_start")
    return StartResponse(session_id=sess.session_id, step=sess.step, message=GREETING)


@app.post("/api/agent/chat", response_model=ChatResponse)
def agent_chat(req: ChatRequest) -> ChatResponse:
    sess = store.get(req.session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="Unknown session")

    user_msg = req.message.strip()
    sess.add_turn("user", user_msg)

    if _is_exit(user_msg):
        sess.step = STEP_DONE
        reply = "Session ended. Click **New Session** to start again."
    elif sess.step in {STEP_GREET, STEP_AWAIT_DATES}:
        reply = _handle_await_dates(sess, user_msg)
    elif sess.step == STEP_CONFIRM:
        reply = _handle_confirm(sess, user_msg)
    elif sess.step == STEP_PROCESSING:
        reply = "Pipeline is already running. Watch the Status Monitor for updates."
    elif sess.step == STEP_ERROR:
        if user_msg.lower() in {"retry", "rerun"}:
            reply = _trigger_pipeline(sess)
        else:
            reply = (
                f"Last error: `{sess.last_error}`. "
                f"Reply `retry` to try again or send a new date range."
            )
            sess.step = STEP_AWAIT_DATES
    else:  # STEP_DONE
        reply = "Session complete. Click **New Session** to start another run."

    sess.add_turn("assistant", reply)
    return ChatResponse(
        session_id=sess.session_id,
        step=sess.step,
        message=reply,
        start_date=sess.start_date,
        end_date=sess.end_date,
        airflow_run_id=sess.airflow_run_id,
    )


# ---------------------------------------------------------------------------
# /api/status
# ---------------------------------------------------------------------------
def _processing_state_for(sess: Session | None) -> str:
    if sess is None:
        return "idle"
    return {
        STEP_PROCESSING: "running",
        STEP_DONE: "complete",
        STEP_ERROR: "error",
    }.get(sess.step, "pending")


def _latest_session() -> Session | None:
    return store.latest()


@app.get("/api/status/summary", response_model=StatusSummary)
def status_summary() -> StatusSummary:
    sess = _latest_session()
    counts = database.fetch_anomaly_summary()
    anomalies_cached = 0
    sd = ed = None
    if sess is not None:
        anomalies_cached = len(sess.analysis.get("anomalies", []))
        sd, ed = sess.start_date, sess.end_date
    if sd is None or ed is None:
        rng = None
        try:
            rng = database.fetch_current_metadata_range()
        except Exception as exc:
            log.warning("metadata range fetch failed: %s", exc)
        if rng:
            sd = sd or str(rng.get("start_date"))
            ed = ed or str(rng.get("end_date"))

    return StatusSummary(
        total_records=counts["total_records"],
        anomalies_detected=anomalies_cached,
        processing_state=_processing_state_for(sess),
        start_date=sd,
        end_date=ed,
        last_updated=datetime.utcnow().isoformat() + "Z",
    )


@app.get("/api/status/contracts")
def status_contracts(limit: int = 200) -> dict[str, Any]:
    """Return per-item status rows. Each anomaly record is a 'contract'."""
    rows = database.fetch_anomaly_rows(limit=limit)
    sess = _latest_session()
    flagged_ids: set[Any] = set()
    if sess is not None:
        for a in sess.analysis.get("anomalies", []):
            if "invoice_id" in a:
                flagged_ids.add(a["invoice_id"])

    contracts: list[ContractRow] = []
    for r in rows:
        rid = r.get("invoice_id") or r.get("id") or r.get("pk")
        status = "flagged" if rid in flagged_ids else "processed"
        contracts.append(ContractRow(id=rid, status=status, fields=r))

    return {
        "count": len(contracts),
        "flagged": len(flagged_ids),
        "contracts": [c.model_dump() for c in contracts],
    }


@app.post("/api/status/ask", response_model=StatusAskResponse)
def status_ask(req: StatusAskRequest) -> StatusAskResponse:
    summary = database.fetch_anomaly_summary()
    rows = database.fetch_anomaly_rows(limit=50)
    answer = llm_service.status_qa(req.question, summary, rows)
    return StatusAskResponse(answer=answer)


# ---------------------------------------------------------------------------
# /api/analysis
# ---------------------------------------------------------------------------
@app.get("/api/analysis/deliveries")
def analysis_deliveries() -> dict[str, list[Delivery]]:
    """Available runs. We surface the latest metadata range as the default delivery."""
    deliveries: list[Delivery] = []
    try:
        rng = database.fetch_current_metadata_range()
        if rng:
            sd = str(rng.get("start_date"))
            ed = str(rng.get("end_date"))
            deliveries.append(
                Delivery(
                    id=f"run_{sd}_{ed}",
                    label=f"{sd} → {ed}",
                    start_date=sd,
                    end_date=ed,
                )
            )
    except Exception as exc:
        log.warning("deliveries fetch failed: %s", exc)

    # also expose latest in-memory session run
    sess = _latest_session()
    if sess and sess.start_date and sess.end_date:
        sid = f"sess_{sess.session_id[:8]}"
        if not any(d.id == sid for d in deliveries):
            deliveries.append(
                Delivery(
                    id=sid,
                    label=f"Session {sess.session_id[:8]} ({sess.start_date} → {sess.end_date})",
                    start_date=sess.start_date,
                    end_date=sess.end_date,
                )
            )
    return {"deliveries": deliveries}


@app.post("/api/analysis/setup", response_model=AnalysisSetupResponse)
def analysis_setup(req: AnalysisSetupRequest) -> AnalysisSetupResponse:
    sess = store.get(req.session_id) if req.session_id else None
    if sess is None:
        sess = store.create()
    sess.log("analysis_setup", {"delivery_id": req.delivery_id})

    rows = database.fetch_anomaly_data()
    metadata = database.fetch_column_metadata()
    column_info = database.format_column_metadata(metadata)
    understanding = llm_service.understand_dataset(rows, column_info)
    anomalies = llm_service.detect_anomalies(rows, understanding, column_info)
    final_output = llm_service.format_report(anomalies)

    sess.analysis = {
        "rows": rows,
        "column_info": column_info,
        "understanding": understanding,
        "anomalies": anomalies,
        "final_output": final_output,
        "metadata": metadata,
    }
    sess.log("analysis_ready", {"anomaly_count": len(anomalies)})

    delivery = Delivery(
        id=req.delivery_id,
        label=f"{req.start_date or sess.start_date} → {req.end_date or sess.end_date}",
        start_date=req.start_date or sess.start_date,
        end_date=req.end_date or sess.end_date,
    )
    return AnalysisSetupResponse(
        session_id=sess.session_id,
        understanding=understanding,
        anomalies=anomalies,
        final_output=final_output,
        column_info=column_info,
        delivery=delivery,
    )


@app.post("/api/analysis/ask", response_model=AnalysisAskResponse)
def analysis_ask(req: AnalysisAskRequest) -> AnalysisAskResponse:
    sess = store.get(req.session_id)
    if sess is None or not sess.analysis:
        raise HTTPException(status_code=400, detail="Analysis not yet set up for this session.")

    analysis = sess.analysis
    answer = llm_service.chat_about_anomalies(
        req.question,
        analysis["anomalies"],
        analysis["understanding"],
        analysis["column_info"],
    )

    # Also try to generate a supporting SQL query for transparency.
    sql = ""
    rows: list[dict[str, Any]] | None = None
    try:
        sql = llm_service.generate_sql(
            req.question,
            analysis["column_info"],
            table_fqn="anomaly.duplicate_ap_invoice",
        )
        if sql:
            rows = database.run_select_safely(sql)
    except Exception as exc:
        log.info("SQL augment skipped: %s", exc)
        sql = sql or ""
        rows = None

    sess.log("analysis_ask", {"question": req.question, "sql": sql})
    return AnalysisAskResponse(answer=answer, sql=sql or None, rows=rows)


# ---------------------------------------------------------------------------
# /api/reports
# ---------------------------------------------------------------------------
@app.post("/api/reports/reconciliation", response_model=ReconciliationResponse)
def reports_reconciliation(req: ReconciliationRequest) -> ReconciliationResponse:
    sess = store.get(req.session_id)
    if sess is None or not sess.analysis:
        raise HTTPException(status_code=400, detail="Run analysis setup first.")

    summary = database.fetch_anomaly_summary()
    anomalies = sess.analysis.get("anomalies", [])
    report = llm_service.reconciliation_report(
        sess.start_date or "n/a",
        sess.end_date or "n/a",
        summary,
        anomalies,
    )
    summary_out = StatusSummary(
        total_records=summary["total_records"],
        anomalies_detected=len(anomalies),
        processing_state=_processing_state_for(sess),
        start_date=sess.start_date,
        end_date=sess.end_date,
        last_updated=datetime.utcnow().isoformat() + "Z",
    )
    sess.log("reconciliation", {"anomaly_count": len(anomalies)})
    return ReconciliationResponse(report=report, summary=summary_out)


@app.get("/api/reports/audit")
def reports_audit() -> dict[str, list[AuditEntry]]:
    return {"entries": [AuditEntry(**e).model_dump() for e in store.all_audit()]}


# ---------------------------------------------------------------------------
# /api/health
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health() -> dict[str, Any]:
    db_ok = True
    try:
        database.run_query("SELECT 1 AS ok")
    except Exception as exc:
        db_ok = False
        log.warning("health: db check failed: %s", exc)
    return {
        "status": "ok",
        "db": "ok" if db_ok else "down",
        "time": datetime.utcnow().isoformat() + "Z",
    }

"""Generate doc/lld_section_01.docx — Section 1: Product Vision & Problem Statement.

Run from repo root:
    python doc/_build/build_section_01.py
"""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from _docx_utils import LLDBuilder  # noqa: E402

OUT = HERE.parent / "lld_section_01.docx"


def build() -> None:
    b = LLDBuilder("Anomaly Agent — LLD Section 1: Product Vision & Problem Statement")

    # ------------------------------------------------------------------ §1
    b.h1("1. Product Vision & Problem Statement")
    b.p(
        "This section anchors why the Anomaly Agent exists, who it serves, what "
        "good looks like, and what it intentionally is not. Every claim is "
        "tagged IMPLEMENTED / PARTIAL / PLANNED against the code on branch "
        "claude/anomaly-agent-frontend-s9ygV."
    )

    # 1.1 -------------------------------------------------------------- Mission
    b.h2("1.1 Mission")
    b.p(
        "Help finance auditors detect duplicate Accounts Payable (AP) invoices "
        "for a chosen date range by combining a curated MySQL warehouse, an "
        "Airflow ingestion pipeline, and an LLM-driven anomaly review — all "
        "behind a single 3-panel web UI."
    )
    b.p("One-sentence form:")
    b.code(
        "\"Pick a date range, run the pipeline, and read an LLM-authored "
        "anomaly report with follow-up Q&A — without leaving the browser.\""
    )
    b.status_table([
        (
            "Date-range driven anomaly run",
            "IMPLEMENTED",
            "backend/main.py::_trigger_pipeline; backend/database.py::upsert_anomaly_metadata",
        ),
        (
            "LLM-authored anomaly report (markdown)",
            "IMPLEMENTED",
            "backend/llm_service.py::format_report + prompts/anomaly_format_prompt.txt",
        ),
        (
            "Follow-up Q&A grounded on the run",
            "IMPLEMENTED",
            "backend/llm_service.py::chat_about_anomalies + /api/analysis/ask",
        ),
        (
            "Mission expanded to other anomaly domains (beyond duplicate AP invoices)",
            "PLANNED",
            "Tables, prompts and reconciliation rules are hard-coded for duplicate_ap_invoice today.",
        ),
    ])

    # 1.2 -------------------------------------------------------------- Target Users
    b.h2("1.2 Target Users")
    b.p("Two personas, in priority order:")

    b.h3("Primary — Finance Auditor (\"the analyst\")")
    b.bullets([
        "Job-to-be-done: confirm whether a given period contains duplicate or "
        "suspicious AP invoices before posting/closing the books.",
        "Pain points: rule-based duplicate detectors over-fire on near-duplicates "
        "(e.g. invoice numbering quirks, vendor aliases) and under-fire on "
        "subtle splits or out-of-pattern amounts.",
        "Tooling today (without this app): SQL ad-hoc queries against the "
        "anomaly.duplicate_ap_invoice table, manual spreadsheets, email "
        "back-and-forth with AP operators.",
    ])

    b.h3("Secondary — AP Operations Lead (\"the operator\")")
    b.bullets([
        "Job-to-be-done: trigger the anomaly DAG for a window, watch it land, "
        "and hand the report off to the auditor.",
        "Pain points: today this is a manual SSH + airflow CLI step on a "
        "shared EC2 host. No visible \"is it done?\" signal short of tailing logs.",
        "What this app gives them: a Confirm button in chat, a status panel that "
        "polls for completion, and an audit trail of who triggered what.",
    ])

    b.status_table([
        ("Auditor — view dataset understanding + anomaly report", "IMPLEMENTED",
         "frontend/src/panels/AnalysisPanel.jsx + /api/analysis/setup"),
        ("Auditor — ask follow-up questions with optional SQL", "IMPLEMENTED",
         "/api/analysis/ask + backend/database.py::run_select_safely"),
        ("Operator — trigger DAG via chat with a Confirm button", "IMPLEMENTED",
         "frontend/src/panels/AgentChatPanel.jsx + backend/airflow_trigger.py"),
        ("Operator — see real Airflow run status (SUCCESS/FAILED), not just \"triggered\"", "PLANNED",
         "Today the SSH call is fire-and-forget; see roadmap Phase 2."),
        ("Distinct sign-in / per-user sessions for these two personas", "PLANNED",
         "No auth layer; session_id is anonymous. doc/roadmap.md Phase 5."),
    ])

    # 1.3 -------------------------------------------------------------- Success Metrics
    b.h2("1.3 Success Metrics")
    b.p(
        "These metrics are not yet instrumented — the app emits Python logs and "
        "an in-memory audit trail, but no metrics pipeline. The list below is the "
        "intended dashboard once telemetry lands (see §21)."
    )

    b.h3("North-star")
    b.bullets([
        "Auditor time-to-anomaly-report: minutes from \"open the app\" to "
        "\"reading a finalized markdown report.\" Target: < 5 minutes for a "
        "12-month window.",
    ])

    b.h3("Leading indicators")
    b.bullets([
        "% of detected anomalies that the auditor accepts as true positives "
        "(thumbs-up rate, PLANNED in §19.4).",
        "Median latency of /api/analysis/setup end-to-end.",
        "Number of follow-up questions per analysis run (engagement signal).",
    ])

    b.h3("Guardrail metrics")
    b.bullets([
        "LLM cost per run (USD).",
        "Backend error rate (5xx) and DB connection failures.",
        "False-positive rate from the anomaly prompt vs. auditor labels.",
    ])

    b.status_table([
        ("Audit trail of session events (in-memory)", "IMPLEMENTED",
         "backend/session_manager.py SessionStore.all_audit + /api/reports/audit"),
        ("Python logging at INFO level", "IMPLEMENTED",
         "backend/main.py logging.basicConfig(...)"),
        ("Metrics pipeline (Prometheus / OpenTelemetry / vendor)", "PLANNED",
         "doc/roadmap.md Phase 6 (\"Production deployment\") + §21 of this LLD."),
        ("LLM cost / token tracking", "PLANNED",
         "No token counting today. §22 of this LLD."),
        ("Auditor feedback capture (thumbs-up/down on anomalies)", "PLANNED",
         "No UI hook for feedback. §19.4 of this LLD."),
    ])

    # 1.4 -------------------------------------------------------------- Non-Goals
    b.h2("1.4 Non-Goals")
    b.p(
        "What the app deliberately does not do today. These are scope guardrails, "
        "not future commitments — moving any item out of this list requires an "
        "explicit roadmap entry."
    )

    b.bullets([
        "Real-time / streaming detection. The app is run-on-demand for a date "
        "range; it does not subscribe to a live invoice stream.",
        "Source-system writes. The SQL guard rejects anything that is not a "
        "SELECT (backend/database.py::run_select_safely). The app never edits the "
        "AP invoice records or any other source table.",
        "General-purpose BI / dashboarding. Charts, pivots, and slice-and-dice "
        "are out of scope; the analyst panel is built for textual review and Q&A.",
        "Automatic remediation. The app flags anomalies but never voids invoices, "
        "creates JIRA tickets, or notifies vendors.",
        "Multi-tenant / multi-organization. Single-tenant assumption baked into "
        "DB schema and CORS config.",
        "Regulatory certification (SOC2, HIPAA, etc.). The app may be deployed "
        "in environments that are certified, but the app itself is not certified "
        "infrastructure today.",
    ])

    b.status_table([
        ("Read-only SQL enforcement (non-goal: writes via Q&A SQL)", "IMPLEMENTED",
         "backend/database.py::run_select_safely rejects non-SELECT and destructive verbs."),
        ("CORS scoped to localhost (non-goal: cross-origin browser callers)", "IMPLEMENTED",
         "backend/main.py CORSMiddleware allow_origins=[\"http://localhost:3000\", \"http://127.0.0.1:3000\"]"),
        ("Single-tenant data scope (non-goal: multi-org partitioning)", "IMPLEMENTED",
         "Hard-coded ANOMALY_TABLE / METADATA_TABLE in backend/config.py; no tenant column."),
        ("Streaming inference / real-time detection", "PLANNED",
         "Polling at 30s today; SSE/WS is a roadmap item (§14)."),
    ])

    # 1.5 -------------------------------------------------------------- Competitive
    b.h2("1.5 Competitive & Strategic Context")

    b.h3("Adjacent approaches & how this app differs")
    b.kv_table([
        ("Manual SQL + spreadsheets (status quo)",
         "What auditors do today. The app preserves this workflow as the "
         "fallback (run_select_safely lets the analyst execute SELECTs surfaced "
         "by the LLM) but layers a guided UI and an LLM narrative on top."),
        ("Rule-based duplicate detectors (e.g. classic AP audit tools)",
         "Strong on exact / near-exact matches; weak on contextual or "
         "vendor-alias anomalies. The LLM step in detect_anomalies (chunked "
         "prompt over 200-row windows) is meant to catch the long-tail cases."),
        ("General-purpose AI data assistants (e.g. ChatGPT + CSV upload)",
         "Flexible but ungrounded — no schema metadata, no audit trail, no "
         "pipeline triggering. This app is opinionated for one job: AP "
         "duplicate review, with citations to invoice_id."),
        ("Sister product — AdminFee Agent",
         "Same architecture (3-panel React + FastAPI + step-based FSM). The "
         "Anomaly Agent reuses the pattern verbatim so a developer fluent in "
         "AdminFee Agent can navigate this codebase on day one."),
    ])

    b.h3("Differentiators (today)")
    b.bullets([
        "Grounded LLM output: every anomaly references invoice_id, severity, "
        "and an evidence object built from real columns "
        "(prompts/anomaly_prompt.txt).",
        "Fail-soft behavior: every LLM call has a regex / deterministic "
        "fallback (backend/llm_service.py), so a model outage degrades the "
        "narrative but never crashes the page.",
        "Audit trail by default: every state transition, metadata write, and "
        "Airflow trigger emits an audit event (backend/session_manager.py "
        "Session.log).",
        "Read-only SQL execution path so the analyst can verify an LLM claim "
        "by running its generated SELECT against the warehouse.",
    ])

    b.h3("Strategic moats (planned, not yet realized)")
    b.bullets([
        "Memory-backed detection — feed previously-confirmed anomalies into "
        "subsequent runs (PLANNED, see §8 and roadmap Phase 1).",
        "Multi-domain support — one runtime, many anomaly tables (PLANNED, "
        "roadmap Phase 4).",
        "Persistent feedback loop — auditor acceptance/rejection labels train "
        "future prompts and evaluation suites (PLANNED, §19.4 + §20.2).",
    ])

    b.status_table([
        ("Architectural parity with AdminFee Agent (3-panel, FSM, /api/* surface)", "IMPLEMENTED",
         "frontend/src/App.jsx, backend/main.py route layout."),
        ("Grounded anomaly output with invoice_id citations", "IMPLEMENTED",
         "prompts/anomaly_prompt.txt + dedupe in backend/llm_service.py::detect_anomalies."),
        ("Auditor-runnable verification SQL", "IMPLEMENTED",
         "backend/llm_service.py::generate_sql + database.run_select_safely (/api/analysis/ask)."),
        ("Memory of prior runs as a moat", "PLANNED",
         "Today memory variable is the literal string \"[]\". roadmap Phase 1."),
        ("Multi-domain anomaly coverage", "PLANNED",
         "Schema + prompts hard-coded for one table. roadmap Phase 4."),
    ])

    b.save(OUT)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    build()

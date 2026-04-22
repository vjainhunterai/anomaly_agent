"""LLM wrapper with normalize / generate SQL / analyze / format helpers.

All prompts live in ../prompts/*.txt. Every LLM call is wrapped with a regex
fallback so the app degrades gracefully if the LLM is unavailable.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_openai import ChatOpenAI

from config import OPENAI_MODEL, OPENAI_TEMPERATURE, PROMPTS_DIR

log = logging.getLogger(__name__)

_llm: ChatOpenAI | None = None


def get_llm() -> ChatOpenAI:
    global _llm
    if _llm is None:
        _llm = ChatOpenAI(model=OPENAI_MODEL, temperature=OPENAI_TEMPERATURE)
    return _llm


# ---------------------------------------------------------------------------
# Prompt loader
# ---------------------------------------------------------------------------
_prompt_cache: dict[str, str] = {}


def load_prompt(name: str) -> str:
    if name not in _prompt_cache:
        path: Path = PROMPTS_DIR / f"{name}.txt"
        _prompt_cache[name] = path.read_text(encoding="utf-8")
    return _prompt_cache[name]


# ---------------------------------------------------------------------------
# Core invoke with graceful failure
# ---------------------------------------------------------------------------
def invoke_llm(prompt: str) -> str:
    try:
        resp = get_llm().invoke(prompt)
        return (resp.content or "").strip()
    except Exception as exc:  # network, auth, rate limit, etc.
        log.exception("LLM invocation failed: %s", exc)
        return ""


def _strip_json_fences(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    return cleaned


# ---------------------------------------------------------------------------
# 1. NORMALIZE: user free-text date range -> {start_date, end_date}
# ---------------------------------------------------------------------------
_DATE_RE = re.compile(r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})")


def _normalize_with_regex(text: str) -> dict[str, str | None]:
    hits = _DATE_RE.findall(text or "")
    norm = [h.replace("/", "-") for h in hits]
    # pad single-digit month/day
    def pad(d: str) -> str:
        y, m, day = d.split("-")
        return f"{y}-{int(m):02d}-{int(day):02d}"

    norm = [pad(d) for d in norm]
    if len(norm) >= 2:
        return {"start_date": norm[0], "end_date": norm[1]}
    if len(norm) == 1:
        return {"start_date": norm[0], "end_date": norm[0]}
    return {"start_date": None, "end_date": None}


def normalize_date_range(user_text: str) -> dict[str, str | None]:
    """LLM-first, regex fallback."""
    prompt = load_prompt("date_extract_prompt").format(input=user_text)
    raw = invoke_llm(prompt)
    if raw:
        try:
            data = json.loads(_strip_json_fences(raw))
            sd = data.get("start_date")
            ed = data.get("end_date")
            if sd and ed:
                return {"start_date": sd, "end_date": ed}
        except Exception as exc:
            log.warning("LLM date JSON parse failed (%s); falling back to regex", exc)
    return _normalize_with_regex(user_text)


def validate_date_range(start_date: str | None, end_date: str | None) -> tuple[bool, str]:
    if not start_date or not end_date:
        return False, "Missing start or end date."
    try:
        s = datetime.strptime(start_date, "%Y-%m-%d")
        e = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        return False, "Dates must be in YYYY-MM-DD format."
    if s > e:
        return False, "Start date is after end date."
    return True, "ok"


# ---------------------------------------------------------------------------
# 2. ANALYZE: understanding + anomaly detection over rows
# ---------------------------------------------------------------------------
def understand_dataset(rows: list[dict[str, Any]], column_info: str) -> str:
    sample = json.dumps(rows[:200], indent=2, default=str)
    prompt = load_prompt("understanding_prompt").format(data=sample, column_info=column_info)
    out = invoke_llm(prompt)
    return out or "Dataset understanding unavailable — LLM did not respond."


def _chunk(seq: list[Any], size: int):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def detect_anomalies(
    rows: list[dict[str, Any]],
    understanding: str,
    column_info: str,
    memory: str = "[]",
    chunk_size: int = 200,
) -> list[dict[str, Any]]:
    all_anomalies: list[dict[str, Any]] = []
    for chunk in _chunk(rows, chunk_size):
        prompt = load_prompt("anomaly_prompt").format(
            data=json.dumps(chunk, indent=2, default=str),
            understanding=understanding,
            memory=memory,
            column_info=column_info,
        )
        raw = invoke_llm(prompt)
        if not raw:
            continue
        try:
            parsed = json.loads(_strip_json_fences(raw))
        except Exception as exc:
            log.warning("Anomaly chunk parse failed: %s", exc)
            continue
        if isinstance(parsed, dict):
            parsed = [parsed]
        for item in parsed:
            if isinstance(item, str):
                try:
                    item = json.loads(item)
                except Exception:
                    continue
            if isinstance(item, dict):
                all_anomalies.append(item)

    # dedupe on invoice_id if present
    unique: dict[Any, dict[str, Any]] = {}
    for a in all_anomalies:
        key = a.get("invoice_id") or a.get("id") or json.dumps(a, sort_keys=True, default=str)
        unique[key] = a
    return list(unique.values())


# ---------------------------------------------------------------------------
# 3. FORMAT: anomalies -> markdown report
# ---------------------------------------------------------------------------
def format_report(anomalies: list[dict[str, Any]]) -> str:
    prompt = load_prompt("anomaly_format_prompt").format(
        anomalies=json.dumps(anomalies, indent=2, default=str)
    )
    out = invoke_llm(prompt)
    if out:
        return out
    # fallback: plain markdown table
    if not anomalies:
        return "**No anomalies detected.**"
    keys = sorted({k for a in anomalies for k in a.keys()})
    header = "| " + " | ".join(keys) + " |"
    divider = "| " + " | ".join("---" for _ in keys) + " |"
    body = "\n".join(
        "| " + " | ".join(str(a.get(k, "")) for k in keys) + " |" for a in anomalies
    )
    return f"### Anomaly Report ({len(anomalies)} records)\n\n{header}\n{divider}\n{body}"


# ---------------------------------------------------------------------------
# 4. CHAT / Q&A
# ---------------------------------------------------------------------------
def chat_about_anomalies(
    question: str,
    anomalies: list[dict[str, Any]],
    understanding: str,
    column_info: str,
) -> str:
    prompt = load_prompt("anomaly_chat_prompt").format(
        question=question,
        anomalies=json.dumps(anomalies, indent=2, default=str),
        understanding=understanding,
        column_info=column_info,
    )
    out = invoke_llm(prompt)
    return out or "I couldn't generate an answer right now. Please try again."


def status_qa(question: str, summary: dict[str, Any], rows_preview: list[dict[str, Any]]) -> str:
    prompt = load_prompt("status_prompt").format(
        question=question,
        summary=json.dumps(summary, indent=2, default=str),
        rows=json.dumps(rows_preview[:50], indent=2, default=str),
    )
    out = invoke_llm(prompt)
    return out or "Status information is temporarily unavailable."


# ---------------------------------------------------------------------------
# 5. SQL GENERATION
# ---------------------------------------------------------------------------
_SQL_FENCE = re.compile(r"```(?:sql)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def generate_sql(question: str, column_info: str, table_fqn: str) -> str:
    prompt = load_prompt("sql_prompt").format(
        question=question, column_info=column_info, table=table_fqn
    )
    raw = invoke_llm(prompt)
    if not raw:
        return ""
    m = _SQL_FENCE.search(raw)
    sql = m.group(1) if m else raw
    return sql.strip().rstrip(";")


# ---------------------------------------------------------------------------
# 6. RECONCILIATION
# ---------------------------------------------------------------------------
def reconciliation_report(
    start_date: str,
    end_date: str,
    summary: dict[str, Any],
    anomalies: list[dict[str, Any]],
) -> str:
    prompt = load_prompt("reconciliation_prompt").format(
        start_date=start_date,
        end_date=end_date,
        summary=json.dumps(summary, indent=2, default=str),
        anomalies=json.dumps(anomalies[:50], indent=2, default=str),
    )
    out = invoke_llm(prompt)
    if out:
        return out
    return (
        f"### Reconciliation summary ({start_date} → {end_date})\n\n"
        f"- Total records scanned: **{summary.get('total_records', 0)}**\n"
        f"- Anomalies detected: **{len(anomalies)}**\n"
    )

"""SQLAlchemy engine + raw SQL helpers for the Anomaly Agent."""
from __future__ import annotations

import logging
from typing import Any, Iterable

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from config import (
    ANOMALY_TABLE,
    ANOMALY_TABLE_NAME,
    COLUMN_INFO_TABLE,
    DB_URI,
    METADATA_TABLE,
)

log = logging.getLogger(__name__)

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(DB_URI, pool_pre_ping=True, pool_recycle=1800)
    return _engine


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------
def run_query(sql: str, params: dict | None = None) -> list[dict[str, Any]]:
    """Execute a SELECT and return rows as list[dict]."""
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(text(sql), params or {})
        return [dict(r) for r in result.mappings()]


def run_execute(sql: str, params: dict | None = None) -> None:
    """Execute a write statement and commit."""
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text(sql), params or {})
        conn.commit()


# ---------------------------------------------------------------------------
# Anomaly-specific helpers
# ---------------------------------------------------------------------------
def upsert_anomaly_metadata(start_date: str, end_date: str) -> None:
    """Replace the single-row metadata table with the newly requested range."""
    run_execute(f"TRUNCATE TABLE {METADATA_TABLE}")
    run_execute(
        f"INSERT INTO {METADATA_TABLE}(start_date, end_date) VALUES(:start_date, :end_date)",
        {"start_date": start_date, "end_date": end_date},
    )


def fetch_anomaly_data() -> list[dict[str, Any]]:
    return run_query(f"SELECT * FROM {ANOMALY_TABLE}")


def fetch_column_metadata(table_name: str = ANOMALY_TABLE_NAME) -> dict[str, Any]:
    rows = run_query(
        f"""SELECT column_name, comments FROM {COLUMN_INFO_TABLE}
            WHERE table_name = :table_name""",
        {"table_name": table_name},
    )
    return {
        "table_name": table_name,
        "table_description": "Accounts Payable duplicate invoice dataset",
        "columns": [
            {"name": r["column_name"], "description": r["comments"]} for r in rows
        ],
    }


def format_column_metadata(metadata: dict[str, Any]) -> str:
    body = (
        f"TABLE INFORMATION:\n\nTable name: {metadata['table_name']}\n\n"
        f"Table Description:\n{metadata['table_description']}\n\nCOLUMN DEFINITIONS:"
    )
    for col in metadata["columns"]:
        body += f"\n{col['name']}: {col['description']}"
    return body.strip()


def fetch_current_metadata_range() -> dict[str, Any] | None:
    rows = run_query(f"SELECT start_date, end_date FROM {METADATA_TABLE} LIMIT 1")
    return rows[0] if rows else None


def fetch_anomaly_summary() -> dict[str, int]:
    """Lightweight counts for the status monitor."""
    try:
        total = run_query(f"SELECT COUNT(*) AS c FROM {ANOMALY_TABLE}")[0]["c"]
    except Exception as exc:  # table missing, DB down, etc.
        log.warning("Unable to fetch anomaly summary: %s", exc)
        total = 0
    return {"total_records": int(total or 0)}


def fetch_anomaly_rows(limit: int = 500) -> list[dict[str, Any]]:
    try:
        return run_query(f"SELECT * FROM {ANOMALY_TABLE} LIMIT :lim", {"lim": limit})
    except Exception as exc:
        log.warning("Unable to fetch anomaly rows: %s", exc)
        return []


def run_select_safely(sql: str) -> list[dict[str, Any]]:
    """Execute an LLM-generated read-only query. Raises on non-SELECT input."""
    normalized = sql.strip().rstrip(";").lower()
    if not normalized.startswith("select"):
        raise ValueError("Only SELECT statements are allowed.")
    forbidden = ("insert ", "update ", "delete ", "drop ", "alter ", "truncate ")
    if any(f in normalized for f in forbidden):
        raise ValueError("Destructive SQL is not allowed.")
    return run_query(sql)

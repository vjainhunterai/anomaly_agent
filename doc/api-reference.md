# API Reference

All routes are served by `backend/main.py`. Status convention applies:
every route below is **IMPLEMENTED** unless tagged otherwise.

- Base URL (dev): `http://localhost:8000`
- Frontend proxy: `http://localhost:3000/api/*`
- Content type: `application/json`
- Auth: **none** (PLANNED -- see `roadmap.md`)
- CORS: `localhost:3000` and `127.0.0.1:3000` only

OpenAPI / Swagger: `http://localhost:8000/docs` is served by FastAPI by
default and reflects the live route set.

---

## Agent (chat panel)

### `POST /api/agent/start`
Create a new session and return the greeting.

Request body: none.

Response:
```json
{
  "session_id": "9b2f5c1f...",
  "step": "await_dates",
  "message": "Hello -- welcome to the **Anomaly Detection Agent**. ..."
}
```

### `POST /api/agent/chat`
Send a user message; advances the FSM.

Request:
```json
{ "session_id": "9b2f5c1f...", "message": "2024-01-01 to 2024-12-31" }
```

Response:
```json
{
  "session_id": "9b2f5c1f...",
  "step": "confirm",
  "message": "I parsed:\n\n- **Start date:** `2024-01-01` ...",
  "start_date": "2024-01-01",
  "end_date": "2024-12-31",
  "airflow_run_id": null
}
```

FSM transitions (see `architecture.md` and `backend/main.py::agent_chat`):

| Current step | Input               | Next step    | Side effect                |
|--------------|---------------------|--------------|----------------------------|
| greet / await_dates | free text   | confirm      | dates parsed + validated   |
| await_dates  | invalid input       | await_dates  | error message              |
| confirm      | confirm/yes/run     | processing -> done/error | metadata write + Airflow trigger |
| confirm      | anything else       | await_dates  | re-parse                   |
| error        | retry / rerun       | done / error | re-trigger pipeline        |
| any          | exit / quit / cancel| done         | session ends               |

---

## Status (centre panel)

### `GET /api/status/summary`
Summary cards for the centre panel.

Response:
```json
{
  "total_records": 12453,
  "anomalies_detected": 17,
  "processing_state": "complete",
  "start_date": "2024-01-01",
  "end_date": "2024-12-31",
  "last_updated": "2026-04-29T10:31:55.123Z"
}
```

`processing_state` values: `idle`, `pending`, `running`, `complete`, `error`.
Mapped from the latest session's FSM step.

### `GET /api/status/contracts?limit=200`
Per-record table for the centre panel.

Response:
```json
{
  "count": 200,
  "flagged": 17,
  "contracts": [
    {
      "id": "INV-0001",
      "status": "flagged",
      "fields": { "invoice_id": "INV-0001", "vendor_name": "...", "amount": "..." }
    }
  ]
}
```

`status` is `"flagged"` if the row's `invoice_id` matches any anomaly
detected in the latest session's analysis cache, otherwise `"processed"`.

### `POST /api/status/ask`
Free-form Q&A about the current status.

Request:
```json
{ "question": "How many high-severity anomalies are there?" }
```

Response:
```json
{ "answer": "There are 4 high-severity anomalies..." }
```

Backed by `prompts/status_prompt.txt`.

---

## Analysis (right panel)

### `GET /api/analysis/deliveries`
Available runs to analyse.

Response:
```json
{
  "deliveries": [
    {
      "id": "run_2024-01-01_2024-12-31",
      "label": "2024-01-01 -> 2024-12-31",
      "start_date": "2024-01-01",
      "end_date": "2024-12-31"
    }
  ]
}
```

Today the source list is the latest row of `anomaly_metadata` plus the
latest in-memory session run. PLANNED: a delivery history table.

### `POST /api/analysis/setup`
Run understanding + chunked anomaly detection + markdown formatting.
Caches the result on the session.

Request:
```json
{
  "session_id": "9b2f5c1f...",
  "delivery_id": "run_2024-01-01_2024-12-31",
  "start_date": "2024-01-01",
  "end_date": "2024-12-31"
}
```

Response:
```json
{
  "session_id": "9b2f5c1f...",
  "understanding": "### Dataset overview\n...",
  "anomalies": [
    { "invoice_id": "INV-0001", "anomaly_type": "duplicate_payment",
      "severity": "high", "reason": "...", "evidence": { } }
  ],
  "final_output": "### Executive Summary\n...",
  "column_info": "TABLE INFORMATION: ...",
  "delivery": { "id": "...", "label": "...", "start_date": "...", "end_date": "..." }
}
```

If `session_id` is omitted, the backend creates a new session and returns
its id.

### `POST /api/analysis/ask`
Follow-up Q&A over the cached analysis. Always returns a natural-language
answer; opportunistically attaches a SQL query plus rows.

Request:
```json
{ "session_id": "9b2f5c1f...", "question": "Which vendor has the most duplicates?" }
```

Response:
```json
{
  "answer": "Vendor `ACME` accounts for 6 of the 17 duplicates...",
  "sql": "SELECT vendor_name, COUNT(*) FROM anomaly.duplicate_ap_invoice ...",
  "rows": [
    { "vendor_name": "ACME", "COUNT(*)": 6 }
  ]
}
```

`sql` and `rows` are nullable. The SQL is executed via
`database.run_select_safely`, which rejects any non-SELECT statement.

---

## Reports

### `POST /api/reports/reconciliation`
Markdown reconciliation report comparing total records to flagged
anomalies. Auto-fired by the analysis panel after `setup`.

Request:
```json
{ "session_id": "9b2f5c1f..." }
```

Response:
```json
{
  "report": "### Reconciliation Summary\nFor 2024-01-01 -> 2024-12-31...",
  "summary": {
    "total_records": 12453,
    "anomalies_detected": 17,
    "processing_state": "complete",
    "start_date": "2024-01-01",
    "end_date": "2024-12-31",
    "last_updated": "..."
  }
}
```

### `GET /api/reports/audit`
Cross-session event log. Newest first.

Response:
```json
{
  "entries": [
    { "session_id": "9b2f5c1f...", "ts": 1714389115.0,
      "event": "airflow_trigger",
      "detail": { "ok": true, "run_id": "anomaly_20260429_103155", "stderr": "" } }
  ]
}
```

PLANNED: persistent storage, filtering by session/user, time-range queries.

---

## Health

### `GET /api/health`
Liveness probe + DB check.

Response:
```json
{ "status": "ok", "db": "ok", "time": "2026-04-29T10:31:55.123Z" }
```

`db` is `"down"` if `SELECT 1` fails. The frontend header badge reads
this on mount.

---

## Error responses

All errors use FastAPI's default shape:

```json
{ "detail": "Run analysis setup first." }
```

Status codes used by this app:

| Code | When |
|------|------|
| 400  | Invalid request shape, or session has no analysis cached yet. |
| 404  | Unknown `session_id`. |
| 500  | Unhandled server error -- check the uvicorn console. |

The frontend wrapper (`frontend/src/services/api.js`) raises a JS `Error`
whose `.message` is `detail` (or `status statusText` if the body is
empty).

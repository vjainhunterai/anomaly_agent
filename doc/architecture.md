# Architecture

Status convention: every section is **IMPLEMENTED** unless the heading or a
specific bullet says otherwise. Planned work is called out inline.

## Big picture

```
+------------------------------------------------------------------+
|                       Browser (Chrome / Edge)                    |
|                                                                  |
|  +--------------+   +-------------------+   +----------------+   |
|  | AgentChat    |   | StatusMonitor     |   | Analysis       |   |
|  | (left panel) |   | (centre panel)    |   | (right panel)  |   |
|  +------+-------+   +---------+---------+   +--------+-------+   |
|         |                     |                      |           |
|         v                     v                      v           |
|                     services/api.js (fetch)                      |
+------------------------------|-----------------------------------+
                               |  /api/* (Vite proxy on :3000)
                               v
+------------------------------------------------------------------+
|                FastAPI app on :8000  (uvicorn --reload)          |
|                                                                  |
|   main.py            session_manager.py     llm_service.py       |
|   (routes + FSM)     (UUID -> Session)      (LangChain-OpenAI    |
|                                              + regex fallbacks)  |
|                                                                  |
|   database.py        airflow_trigger.py     config.py            |
|   (SQLAlchemy 2)     (Paramiko SSH)         (.env loader)        |
+----------|--------------------|---------------------|------------+
           |                    |                     |
           v                    v                     v
     +-----------+        +-----------+         +------------+
     | MySQL RDS |        |  Airflow  |         |  OpenAI    |
     | joblog_   |        | (Ubuntu   |         |  Chat API  |
     | metadata  |        | EC2 host) |         |            |
     +-----------+        +-----------+         +------------+
```

PLANNED additions to this picture: a persistent session store
(Postgres/Redis), an Airflow REST polling loop, an SSE/WebSocket channel for
push updates, and an optional S3 ingestion path. None of these exist on the
current branch.

## Process model

| Process | Port | Owner | How it starts |
|---------|------|-------|---------------|
| FastAPI / uvicorn | 8000 | Backend | `python run_backend.py` |
| Vite dev server  | 3000 | Frontend | `npm run dev` |
| Browser           | n/a  | User | navigate to `http://localhost:3000` |

The Vite dev server proxies `/api/*` to `http://localhost:8000` -- see
`frontend/vite.config.js`. CORS in `backend/main.py` also allows
`http://localhost:3000` so the same code works if you call the backend
directly from the browser without the proxy.

## Frontend panel responsibilities

### `App.jsx`
- Holds three pieces of shared state: `activeDelivery`, `activeContracts`,
  `processingComplete`.
- Owns the "New Session" button. Reset is implemented by bumping a
  `resetKey`, which is passed as the `key` prop on each panel; React
  unmounts and re-creates the children, wiping their internal state.
- Pings `/api/health` on mount and renders a header badge.

### `AgentChatPanel`
- Calls `POST /api/agent/start` once on mount, stores the returned
  `session_id`, and renders the greeting from the backend.
- For every user message, calls `POST /api/agent/chat` with the session id;
  the backend's reply contains the new step, a markdown-rendered
  assistant message, and (when validated) `start_date` / `end_date`,
  which are pushed up to `App` via `onRangeSelected`.
- Shows a `step-chip` reflecting the FSM step. Quick-reply buttons appear
  only on the `confirm` step.

### `StatusMonitorPanel`
- Polls every 30 seconds (`POLL_MS`) by bumping a `tick` state.
- Renders 4 status cards and a contracts table (first 50 rows, first 8
  columns) sourced from `/api/status/summary` and `/api/status/contracts`.
- Detects completion with two refs: `processingStartedRef` flips to true
  on `running` / `pending`, and `completionFiredRef` ensures the
  `onProcessingComplete` callback fires only once per run.
- Has an inline "Ask" box that calls `/api/status/ask`.

### `AnalysisPanel`
- Lists deliveries from `/api/analysis/deliveries`. Pre-selects whichever
  delivery the chat panel produced.
- When the status monitor reports completion (via the `processingComplete`
  prop), an `autoFiredRef` guard runs `runSetup` exactly once.
- `runSetup` posts to `/api/analysis/setup`, which executes the entire
  understanding -> chunked anomaly detection -> markdown format pipeline
  on the backend, then immediately fires `/api/reports/reconciliation`.
- Free-form Q&A appends to a `qa` list. Each entry can include an
  expandable SQL block plus a sample of returned rows.

## Backend layers

### `session_manager.py`
Plain Python `dict` keyed by UUID, guarded by a `threading.Lock`. Each
`Session` carries:

- `step`, `start_date`, `end_date`
- `history` (list of `ChatTurn`)
- `airflow_run_id`, `airflow_status`
- `analysis` cache (rows, column_info, understanding, anomalies,
  final_output)
- `audit` event log

Persistence: in-process only. PLANNED: move to Postgres or Redis so a
restart doesn't drop sessions.

### `main.py`
Owns all HTTP routes. Two notable internal helpers:

- `_handle_*` functions implement the FSM transitions. They are pure
  functions of `(Session, user_message) -> reply_string`; they mutate the
  session in place.
- `_trigger_pipeline` is the one place that writes to the metadata table
  and invokes Airflow. Called only from STEP_CONFIRM and from the explicit
  `retry` keyword in STEP_ERROR.

### `llm_service.py`
Each public function has the same shape: build prompt from
`prompts/<name>.txt`, call `invoke_llm`, parse, fall back deterministically
on failure.

```
normalize_date_range  -> regex fallback        (date_extract_prompt)
understand_dataset    -> placeholder string    (understanding_prompt)
detect_anomalies      -> empty list            (anomaly_prompt)
format_report         -> regex markdown table  (anomaly_format_prompt)
chat_about_anomalies  -> "couldn't generate"   (anomaly_chat_prompt)
status_qa             -> "unavailable" string  (status_prompt)
generate_sql          -> empty string          (sql_prompt)
reconciliation_report -> static markdown       (reconciliation_prompt)
```

The fallbacks mean the UI degrades but never crashes when the LLM is
unreachable.

### `database.py`
- `get_engine` lazily constructs the SQLAlchemy engine with
  `pool_pre_ping=True` and a 30-minute recycle, then memoizes it.
- `run_select_safely(sql)` is the SQL guard: it lower-cases, strips
  trailing `;`, requires the statement to start with `select`, and
  rejects any of `insert`, `update`, `delete`, `drop`, `alter`,
  `truncate`. Used by the analyst panel's auto-generated SQL.

### `airflow_trigger.py`
- One function `trigger_airflow_dag(run_id) -> TriggerResult`.
- Uses Paramiko with `AutoAddPolicy` and a key file at `SSH_KEY_PATH`.
- Captures stdout, stderr, exit status; the chat panel forwards stderr to
  the user when `ok=False`.

PLANNED: poll the Airflow REST API after triggering so the chat panel can
report SUCCESS / FAILED instead of just "triggered".

## Data flow: a complete run

1. **User opens the page.** `App.jsx` mounts -> health check fires ->
   `AgentChatPanel` calls `POST /api/agent/start`. A `Session` is created
   in `SessionStore` with `step=await_dates`.
2. **User types `"2024-01-01 to 2024-12-31"`.** Frontend calls
   `POST /api/agent/chat`. Backend runs `normalize_date_range` (LLM, regex
   fallback), `validate_date_range`, transitions to `step=confirm`, and
   returns a confirmation message.
3. **User clicks "Confirm & run".** Backend's `_trigger_pipeline` runs
   `upsert_anomaly_metadata`, generates a `run_id`, calls
   `trigger_airflow_dag`, and transitions to `step=done` (or
   `step=error`).
4. **Status monitor sees the transition.** Its 30-second poll picks up
   `processing_state="complete"` from `/api/status/summary` (the helper
   maps the FSM step to a state label). The `completionFiredRef` guard
   fires `onProcessingComplete(contracts)`.
5. **App.jsx forwards completion to the analyst.** `processingComplete`
   becomes `true`. `AnalysisPanel`'s `autoFiredRef` guard calls
   `runSetup`, which posts to `/api/analysis/setup`. The backend fetches
   the duplicate-AP-invoice rows, builds column metadata, runs the
   understanding prompt, runs the chunked anomaly prompt, formats the
   report, and stashes the result in `Session.analysis`.
6. **Reconciliation auto-fires.** `AnalysisPanel` immediately calls
   `/api/reports/reconciliation` with the same session id. The backend
   produces a markdown report and returns it alongside the summary.
7. **User asks a follow-up.** Frontend posts to `/api/analysis/ask`. The
   backend always answers with `chat_about_anomalies`; it additionally
   tries `generate_sql` -> `run_select_safely`. If the SQL succeeds, rows
   ride along in the response and render under a `<details>` block.

## Key design choices

- **State machine in Python, not LangGraph.** The original scripts use
  LangGraph; the web backend uses a plain dict-based FSM so the UI can
  drive transitions one HTTP call at a time. The LangGraph scripts are
  preserved at the repo root for reference.
- **Polling, not push.** Server-Sent Events would be cleaner; polling was
  chosen because it works behind every corporate proxy and needs zero
  infrastructure. Moving to SSE is on the roadmap.
- **Regex fallbacks everywhere.** Every LLM call has a non-LLM fallback so
  the demo still works during a network outage or a quota issue.
- **No third-party UI library.** Plain CSS variables + a hand-rolled
  markdown renderer keep the bundle small and dependencies low.
- **In-memory sessions.** Acceptable for an MVP that one user runs
  locally; not acceptable in production. Tracked in `roadmap.md`.

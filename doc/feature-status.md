# Feature Status — What Is in the Code vs What Is Planned

This is the source of truth for what works today on
`claude/anomaly-agent-frontend-s9ygV`. Every IMPLEMENTED row cites the
file that backs it. Every PLANNED row is intentionally not in the code yet.

Status legend:
- **IMPLEMENTED** — wired end-to-end, runs when LLM + MySQL are reachable.
- **PARTIAL** — present but limited (e.g. regex fallback only, hard-coded
  table, no persistence).
- **PLANNED** — not in this branch.

---

## 1. Conversational Agent (Chat panel)

| Feature | Status | Where it lives / Notes |
|---------|--------|------------------------|
| Step-based FSM (`await_dates -> confirm -> processing -> done / error`) | IMPLEMENTED | `backend/session_manager.py`, `backend/main.py` `_handle_*` |
| LLM date-range extraction from free text | IMPLEMENTED | `backend/llm_service.py::normalize_date_range` + `prompts/date_extract_prompt.txt` |
| Regex fallback when the LLM is unreachable or returns bad JSON | IMPLEMENTED | `backend/llm_service.py::_normalize_with_regex` |
| Date validation (ISO format, start <= end) | IMPLEMENTED | `backend/llm_service.py::validate_date_range` |
| `confirm` / `cancel` quick replies | IMPLEMENTED | `frontend/src/panels/AgentChatPanel.jsx` (quick-replies block) |
| `retry` after a failed Airflow trigger | IMPLEMENTED | `backend/main.py` `agent_chat` STEP_ERROR branch |
| Multi-turn conversation history (per session) | IMPLEMENTED | `Session.history` in `backend/session_manager.py` |
| LangGraph-based chat flow | NOT USED | Documented in `anomaly_processing_agent.py` for reference. The web app uses a hand-rolled FSM instead, so the UI can stay thin. |
| Persistent session history across server restarts | PLANNED | Today the session store is an in-memory `dict`. |
| User authentication / per-user sessions | PLANNED | No auth layer yet; `session_id` is anonymous. |
| Voice input | PLANNED | |

## 2. Anomaly Pipeline Trigger

| Feature | Status | Where it lives / Notes |
|---------|--------|------------------------|
| Truncate + insert into `anomaly_metadata` with the chosen range | IMPLEMENTED | `backend/database.py::upsert_anomaly_metadata` |
| SSH trigger of the remote Airflow DAG | IMPLEMENTED | `backend/airflow_trigger.py` (Paramiko, key-based auth) |
| Generated `run_id` per trigger | IMPLEMENTED | `backend/main.py::_trigger_pipeline` |
| Failure surfaced back into chat with `stderr` | IMPLEMENTED | `backend/main.py::_trigger_pipeline` STEP_ERROR branch |
| Configurable DAG name + remote command via env | IMPLEMENTED | `AIRFLOW_CMD` env, `backend/config.py` |
| Polling Airflow for *real* run status (currently fire-and-forget) | PLANNED | Today the chat reports "triggered"; it does not query Airflow's REST API for the eventual SUCCESS / FAILED state. |
| Retry policy with backoff on SSH failure | PLANNED | Single attempt, no retries. |
| Multiple concurrent runs | PARTIAL | The chat FSM allows it (each session is independent), but the metadata table is a single-row truncate-and-insert, so the latest range overwrites the previous. |

## 3. Status Monitor (centre panel)

| Feature | Status | Where it lives / Notes |
|---------|--------|------------------------|
| 30-second polling of `/api/status/summary` and `/api/status/contracts` | IMPLEMENTED | `frontend/src/panels/StatusMonitorPanel.jsx` `POLL_MS` |
| 4 status cards: records, anomalies, range, state | IMPLEMENTED | same file, `cards` memo |
| Per-record table with flagged-vs-processed row tinting | IMPLEMENTED | same file, `ContractsTable` |
| Manual "Refresh" button | IMPLEMENTED | same file |
| Ref-gated `onProcessingComplete` (fires exactly once per run) | IMPLEMENTED | `processingStartedRef` + `completionFiredRef` |
| Free-form status Q&A via `/api/status/ask` | IMPLEMENTED | `backend/llm_service.py::status_qa` + `prompts/status_prompt.txt` |
| Real-time push instead of polling | PLANNED | Server-Sent Events / WebSocket transport. |
| Per-DAG-task progress bars | PLANNED | Requires Airflow REST API integration first. |
| Filtering / sorting the records table | PLANNED | The table renders the first 50 rows of the first 8 columns. |

## 4. Analyst Panel (right panel)

| Feature | Status | Where it lives / Notes |
|---------|--------|------------------------|
| Delivery picker populated from `/api/analysis/deliveries` | IMPLEMENTED | `frontend/src/panels/AnalysisPanel.jsx` |
| Manual "Run analysis" trigger | IMPLEMENTED | same file |
| Auto-run on `processingComplete` | IMPLEMENTED | `autoFiredRef` guards single fire |
| Dataset understanding (LLM) | IMPLEMENTED | `llm_service.understand_dataset` + `prompts/understanding_prompt.txt` |
| Chunked anomaly detection (size 200) | IMPLEMENTED | `llm_service.detect_anomalies` + `prompts/anomaly_prompt.txt` |
| Markdown anomaly report with regex-table fallback | IMPLEMENTED | `llm_service.format_report` + `prompts/anomaly_format_prompt.txt` |
| Auto-fired reconciliation report after setup | IMPLEMENTED | `AnalysisPanel.jsx::fireReconciliation` -> `/api/reports/reconciliation` |
| Follow-up Q&A grounded on understanding + anomalies | IMPLEMENTED | `llm_service.chat_about_anomalies` |
| Optional SQL generation per question, executed via `run_select_safely` | IMPLEMENTED | `llm_service.generate_sql` + `database.run_select_safely` |
| Read-only SQL guard (rejects non-SELECT, refuses destructive verbs) | IMPLEMENTED | `database.run_select_safely` |
| Persistent memory file across sessions (`memory.json` referenced in original script) | PLANNED | The web backend keeps memory in-process only; `MEMORY_FILE` from `anomaly_analyst.py` is not wired into FastAPI yet. |
| Export anomaly report to CSV / Excel / PDF | PLANNED | |
| Side-by-side compare two deliveries | PLANNED | |
| Highlighting / drill-down on a single anomaly row | PLANNED | |

## 5. Data Layer

| Feature | Status | Where it lives / Notes |
|---------|--------|------------------------|
| MySQL connectivity via SQLAlchemy 2 + PyMySQL | IMPLEMENTED | `backend/database.py::get_engine` |
| `anomaly_metadata` upsert | IMPLEMENTED | `database.upsert_anomaly_metadata` |
| `anomaly.duplicate_ap_invoice` SELECT (full + limited) | IMPLEMENTED | `database.fetch_anomaly_data`, `fetch_anomaly_rows` |
| `table_column_info` lookup for column descriptions | IMPLEMENTED | `database.fetch_column_metadata` |
| Hard-coded table names (overridable via env) | PARTIAL | `ANOMALY_TABLE`, `METADATA_TABLE`, `COLUMN_INFO_TABLE`, `ANOMALY_TABLE_NAME` are all env-configurable, but only one anomaly table is supported per server process. |
| Multi-table / multi-domain anomaly support | PLANNED | UI and backend both assume the duplicate-AP-invoice schema. |
| Connection pooling (SQLAlchemy default) with `pool_pre_ping` and 30-min recycle | IMPLEMENTED | `database.get_engine` |
| Migrations / DDL automation | PLANNED | The schema is assumed to already exist on the RDS instance. |
| S3 ingestion via Boto3 | PLANNED | `boto3` is pinned in `requirements.txt` but no S3 code path is active yet. |

## 6. LLM Layer

| Feature | Status | Where it lives / Notes |
|---------|--------|------------------------|
| LangChain-OpenAI ChatOpenAI wrapper, model swappable via env | IMPLEMENTED | `backend/llm_service.py::get_llm` + `OPENAI_MODEL` env |
| Prompt files loaded from `prompts/*.txt` with in-memory caching | IMPLEMENTED | `backend/llm_service.py::load_prompt` |
| JSON-fence stripping for LLM responses | IMPLEMENTED | `_strip_json_fences` |
| Graceful failure on LLM error (returns empty string, panel falls back) | IMPLEMENTED | `invoke_llm` try/except |
| Regex / deterministic fallbacks for: date extraction, anomaly format, reconciliation | IMPLEMENTED | `llm_service.py` |
| Ollama / local-model backend (commented out in original scripts) | PLANNED | The hooks exist in the legacy scripts; the FastAPI wrapper is OpenAI-only today. |
| Streaming token output to the UI | PLANNED | Requests are blocking. |
| Token / cost tracking and per-session telemetry | PLANNED | |
| Prompt-caching on Anthropic / OpenAI APIs | PLANNED | |

## 7. Reports & Audit

| Feature | Status | Where it lives / Notes |
|---------|--------|------------------------|
| `/api/reports/reconciliation` markdown summary | IMPLEMENTED | `prompts/reconciliation_prompt.txt` + `llm_service.reconciliation_report` |
| `/api/reports/audit` cross-session event log | IMPLEMENTED | `session_manager.SessionStore.all_audit` |
| Audit events written by chat, metadata write, Airflow trigger, analysis setup, reconciliation | IMPLEMENTED | grep `sess.log(` in `backend/main.py` |
| Persistent audit storage (database / file) | PLANNED | Today the audit lives in process memory only. |
| Per-user / per-role audit views | PLANNED | |

## 8. Frontend Shell

| Feature | Status | Where it lives / Notes |
|---------|--------|------------------------|
| 3-panel layout (Chat / Status / Analysis) | IMPLEMENTED | `frontend/src/App.jsx` |
| Shared state: `activeDelivery`, `activeContracts`, `processingComplete` | IMPLEMENTED | same file |
| "New Session" button that resets all panels | IMPLEMENTED | `App.jsx::handleNewSession` (uses `key` prop reset) |
| Health badge on the header | IMPLEMENTED | `HealthBadge` in `App.jsx` |
| Custom markdown renderer (headings, bold, code, lists, tables) | IMPLEMENTED | `frontend/src/components/MarkdownRenderer.jsx` |
| Dark theme via CSS variables | IMPLEMENTED | `frontend/src/index.css` `:root` |
| Responsive collapse at 1200 px / 760 px | IMPLEMENTED | media queries at the bottom of `index.css` |
| Light-theme toggle | PLANNED | |
| i18n / localisation | PLANNED | |
| Tests (Vitest / React Testing Library) | PLANNED | |

## 9. Operations & Deployment

| Feature | Status | Where it lives / Notes |
|---------|--------|------------------------|
| Single-machine local dev (Vite + uvicorn `--reload`) | IMPLEMENTED | `run_backend.py`, `frontend/vite.config.js` |
| `.env` driven configuration | IMPLEMENTED | `backend/config.py` + `.env.example` |
| Windows admin run instructions | IMPLEMENTED | `doc/setup-windows.md` |
| Pinned dependencies | IMPLEMENTED | `backend/requirements.txt`, `frontend/package.json` |
| Docker / docker-compose | PLANNED | |
| CI pipeline (lint / test / build) | PLANNED | |
| Production WSGI/ASGI deployment (gunicorn + nginx) | PLANNED | |
| HTTPS / TLS termination | PLANNED | |
| Secrets in a vault (currently `.env`) | PLANNED | The repo also contains a hard-coded API key in the legacy scripts -- see `doc/roadmap.md` for the cleanup task. |

## 10. Security

| Feature | Status | Where it lives / Notes |
|---------|--------|------------------------|
| CORS locked to `localhost:3000` | IMPLEMENTED | `backend/main.py` `CORSMiddleware` |
| Read-only SQL guard | IMPLEMENTED | `backend/database.py::run_select_safely` |
| Cryptography (Fernet) dependency available | PARTIAL | `cryptography==43.0.3` is pinned; no Fernet code path is active yet. |
| Auth (OAuth, SSO, API tokens) | PLANNED | |
| Rate limiting | PLANNED | |
| Audit log signing | PLANNED | |
| Input validation beyond Pydantic models | PLANNED | |

---

## Summary

**Implemented today:** end-to-end MVP -- chat-driven date entry, MySQL
metadata write, SSH-based Airflow trigger, polled status monitor, automated
LLM analysis with reconciliation, follow-up Q&A with safe SQL, in-memory
audit, markdown rendering, Windows admin run instructions.

**Largest planned gaps:** persistent session/audit storage, real Airflow
status feedback (vs fire-and-forget), authentication, multi-table support,
S3 ingestion, streaming LLM output, Docker/CI for production, and Fernet
encryption for credentials.

See [`roadmap.md`](./roadmap.md) for the phased plan that turns the PLANNED
rows above into milestones.

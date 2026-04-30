# Anomaly Agent — Low-Level Design (LLD)

> Source template: [`doc/lld.md`](./lld.md). This file fills the template
> in section by section against the actual code on branch
> `claude/anomaly-agent-frontend-s9ygV`.
>
> For every subsection one of two labels is used:
>
> - **Applicable** — the subsection is meaningful for the Anomaly Agent.
>   Content distinguishes **In code today** from **Future**.
> - **NA** — the subsection is not meaningful for this application
>   (e.g. multi-agent coordination, RAG). A one-line justification is
>   given so the reader knows it was considered, not skipped.
>
> Sections will be added one at a time.

---

# Part I — Strategy & Identity

## 1. Product Vision & Problem Statement

### 1.1 Mission — *Applicable*

**In code today.** The Anomaly Agent helps a finance auditor detect
duplicate Accounts Payable (AP) invoices for a chosen date range by
combining a curated MySQL warehouse, an Airflow ingestion pipeline, and
an LLM-driven anomaly review — all behind a single 3-panel web UI.

One-sentence statement of mission:

> *"Pick a date range, run the pipeline, and read an LLM-authored anomaly
> report with follow-up Q&A — without leaving the browser."*

The mission is realised end-to-end on the branch:

| Mission element | Where it lives in code |
|-----------------|------------------------|
| Date-range driven anomaly run | `backend/main.py::_trigger_pipeline`; `backend/database.py::upsert_anomaly_metadata` |
| LLM-authored anomaly report | `backend/llm_service.py::format_report` + `prompts/anomaly_format_prompt.txt` |
| Follow-up Q&A grounded on the run | `backend/llm_service.py::chat_about_anomalies` + `POST /api/analysis/ask` |

**Future.** The mission scope is intentionally narrow today — only
duplicate AP invoices over the `anomaly.duplicate_ap_invoice` table.
Broadening to other anomaly domains (vendor master, GL postings, expense
reports) is on the roadmap (Phase 4 in `doc/roadmap.md`) but is not in
the code on this branch.

### 1.2 Target Users — *Applicable*

Two personas, in priority order.

#### Primary — Finance Auditor ("the analyst")

**In code today.**
- Job-to-be-done: confirm whether a given period contains duplicate or
  suspicious AP invoices before posting / closing the books.
- Pain point: rule-based duplicate detectors over-fire on near-duplicates
  (numbering quirks, vendor aliases) and under-fire on subtle splits or
  out-of-pattern amounts.
- What this app gives them:
  - A guided 3-step chat to start a run (`AgentChatPanel.jsx`).
  - An LLM dataset understanding + anomaly report
    (`AnalysisPanel.jsx` → `/api/analysis/setup`).
  - Follow-up Q&A with optional safe SQL execution
    (`/api/analysis/ask` + `database.run_select_safely`).

#### Secondary — AP Operations Lead ("the operator")

**In code today.**
- Job-to-be-done: trigger the anomaly DAG for a window, watch it land,
  and hand the report off to the auditor.
- Pain point (without this app): manual SSH + Airflow CLI on a shared
  EC2 host; no visible "is it done?" signal short of tailing logs.
- What this app gives them:
  - A `Confirm` button that triggers the DAG via Paramiko
    (`backend/airflow_trigger.py`).
  - A status panel that polls every 30 s and surfaces the run state
    (`StatusMonitorPanel.jsx`, `POLL_MS = 30_000`).
  - An audit trail of who triggered what
    (`session_manager.Session.log` + `/api/reports/audit`).

**Future.**
- Distinct sign-in / per-user sessions for the two personas. Today the
  `session_id` is anonymous. See roadmap Phase 5 (auth + multi-tenant).
- Real Airflow run status (`SUCCESS` / `FAILED`), not just *"triggered"*.
  Today the SSH call is fire-and-forget. See roadmap Phase 2.
- Role-based controls so an analyst cannot trigger the pipeline and an
  operator cannot view the analyst's notes. PLANNED.

### 1.3 Success Metrics — *Applicable*

The metrics below are the *intended* dashboard. Today the app emits
Python logs and an in-memory audit trail; there is no metrics pipeline
on this branch.

#### North-star (intended)

- **Auditor time-to-anomaly-report**: minutes from "open the app" to
  "reading a finalised markdown report." Target: **< 5 minutes** for a
  12-month window.

#### Leading indicators (intended)

- % of detected anomalies the auditor accepts as true positives.
- Median end-to-end latency of `/api/analysis/setup`.
- Number of follow-up questions per analysis run.

#### Guardrail metrics (intended)

- LLM cost per run (USD).
- Backend error rate (5xx) and DB connection failure count.
- False-positive rate from the anomaly prompt vs. auditor labels.

#### What is in code today

| Item | Where it lives |
|------|----------------|
| Audit trail of session events (in-memory) | `backend/session_manager.py` `SessionStore.all_audit` + `/api/reports/audit` |
| Python logging at INFO level | `backend/main.py` `logging.basicConfig(...)` |

#### Future

- Metrics pipeline (Prometheus / OpenTelemetry / vendor). PLANNED — see
  §21 of this LLD and roadmap Phase 6.
- LLM cost / token tracking. PLANNED — §22.
- Auditor feedback capture (thumbs-up / thumbs-down). PLANNED — §19.4.

### 1.4 Non-Goals — *Applicable*

What the app deliberately does **not** do today. Moving any item out of
this list requires an explicit roadmap entry.

| Non-goal | How the code enforces it |
|----------|--------------------------|
| Source-system writes | `backend/database.run_select_safely` rejects any non-`SELECT` and any of `insert/update/delete/drop/alter/truncate`. |
| Cross-origin browser callers | `backend/main.py` CORS allow_origins = `["http://localhost:3000", "http://127.0.0.1:3000"]`. |
| Multi-tenant data scope | Single-tenant assumption baked into `ANOMALY_TABLE`, `METADATA_TABLE` in `backend/config.py`. No tenant column in the schema. |
| Real-time / streaming detection | Run-on-demand for a date range; `StatusMonitorPanel.jsx` polls — no event subscription. |
| General-purpose BI / dashboarding | Three panels are textual review + Q&A only; no charts, pivots, or slice-and-dice. |
| Automatic remediation | The app never voids invoices, creates tickets, or notifies vendors. |
| Regulatory certification of the app itself | The app may run inside a certified environment, but the app is not certified infrastructure. |

**Future.** Streaming inference and SSE / WebSocket pushes are tracked
in §14 but explicitly out of scope for the current branch.

### 1.5 Competitive & Strategic Context — *Applicable*

#### Adjacent approaches

| Approach | Where the Anomaly Agent differs |
|----------|---------------------------------|
| Manual SQL + spreadsheets (status quo) | Preserved as the verification path: `run_select_safely` lets the auditor execute the LLM's generated `SELECT` against the warehouse. The app adds a guided UI and an LLM narrative on top. |
| Rule-based duplicate detectors (classic AP audit tools) | Strong on exact / near-exact matches; weak on contextual or vendor-alias anomalies. The chunked LLM step in `detect_anomalies` (200-row windows) targets the long-tail cases. |
| General-purpose AI data assistants (e.g. ChatGPT + CSV upload) | Flexible but ungrounded — no schema metadata, no audit trail, no pipeline triggering. This app is opinionated for one job: AP duplicate review, with citations to `invoice_id`. |
| Sister product — AdminFee Agent | Same architecture (3-panel React + FastAPI + step-based FSM). Reused verbatim so a developer fluent in AdminFee Agent can navigate this codebase on day one. |

#### Differentiators in code today

- **Grounded LLM output.** Every anomaly references `invoice_id`,
  severity, and an evidence object built from real columns
  (`prompts/anomaly_prompt.txt`).
- **Fail-soft behaviour.** Every LLM call has a regex / deterministic
  fallback (`backend/llm_service.py`) — a model outage degrades the
  narrative but never crashes the page.
- **Audit trail by default.** Every state transition, metadata write,
  and Airflow trigger emits an audit event
  (`backend/session_manager.Session.log`).
- **Read-only verification SQL.** The auditor can re-run the LLM's SQL
  against the warehouse to confirm a claim
  (`/api/analysis/ask` + `database.run_select_safely`).

#### Strategic moats — *Future*

- **Memory-backed detection.** Feed previously-confirmed anomalies into
  subsequent runs. Today the `memory` variable is the literal string
  `"[]"` (`backend/llm_service.detect_anomalies`). PLANNED — §8 +
  roadmap Phase 1.
- **Multi-domain anomaly coverage.** One runtime, many tables. PLANNED
  — roadmap Phase 4.
- **Persistent feedback loop.** Auditor accept/reject labels train
  future prompts and eval suites. PLANNED — §19.4 + §20.2.

---

*Last updated for branch `claude/anomaly-agent-frontend-s9ygV`. Sections
2 and beyond will be added in subsequent commits.*

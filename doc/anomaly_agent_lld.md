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

## 2. Agent Identity, Persona & Voice

### 2.1 Persona Definition — *Applicable*

**In code today.**

| Attribute | Value |
|-----------|-------|
| Name (user-facing) | "Anomaly Detection Agent" |
| Internal product name | Anomaly Agent (sister product to AdminFee Agent) |
| Role | Specialist assistant for duplicate-AP-invoice anomaly review |
| Expertise level | Finance audit + MySQL data review; not a general-purpose chatbot |
| Tone | Direct, professional, audit-grade |
| Register | Business-formal; markdown formatting (lists, tables, code spans) |
| Speaking voice | First-person singular when greeting; otherwise impersonal report style |
| Anchor strings | `GREETING` constant in `backend/main.py` defines the opening turn verbatim |

The greeting that establishes the persona on every new session
(`backend/main.py`):

```text
Hello — welcome to the **Anomaly Detection Agent**.
Please provide a date range (e.g. `2024-12-25 to 2025-12-25`)
or type `exit` to quit.
```

The persona is reinforced by every prompt under `prompts/` — each opens
with a role line such as *"You are the Anomaly Agent's analyst chatbot"*
or *"You are an anomaly detection engine for an Accounts Payable
duplicate invoice dataset."*

**Future.**

- Configurable persona / multi-persona support (e.g. *strict auditor*
  vs. *explainer* mode). Today the persona is hard-coded in prompt
  files. PLANNED — see §5.1 and roadmap Phase 4.
- Localised persona (non-English variants). All prompts and fixed
  strings are English-only. PLANNED.

### 2.2 Voice & Style Guide — *Applicable*

#### Defaults enforced by prompts (in code today)

| Style rule | Where it lives |
|------------|----------------|
| Sentence length: short. *"Direct, 2–6 sentences"* | `prompts/anomaly_chat_prompt.txt` |
| Sentence length: *"1–4 sentences"* | `prompts/status_prompt.txt` |
| Length cap: *"under ~250 words"* | `prompts/reconciliation_prompt.txt` |
| Formality: business-formal, no slang, no humor | All prompts |
| Markdown required (no HTML) | `prompts/anomaly_format_prompt.txt` |
| Citations: always reference `invoice_id` for specific records | `prompts/anomaly_chat_prompt.txt` |
| Required headings (4 sections) for the anomaly report | `prompts/anomaly_format_prompt.txt` |
| Required headings (5 sections) for the reconciliation report | `prompts/reconciliation_prompt.txt` |

#### Frontend rendering rules (in code today)

- Markdown is parsed by a hand-rolled component
  (`frontend/src/components/MarkdownRenderer.jsx`).
- Supported: H1–H4 (rendered as H2–H5 to avoid clashing with panel
  headings), bold, italic, inline code, fenced code blocks, ordered /
  unordered lists, GitHub-style tables, links.
- All inline content is HTML-escaped before tag injection — there is no
  path for an LLM response to inject `<script>` tags.
- Code blocks render with a `lang-<name>` class; the SQL view in the
  analyst panel exploits this for `lang-sql` styling.
- Long status answers and reconciliation reports scroll inside the
  panel, not the page (see `.analysis-output` overflow rule in
  `frontend/src/index.css`).

#### Known inconsistency

- **Emoji policy.** `backend/main.py` uses `✅`, `⚠️`, `❌` glyphs in
  three fixed assistant strings (pipeline triggered, soft failure, hard
  failure). Prompts neither encourage nor explicitly forbid emoji in
  LLM output. Status: **PARTIAL** — works, but is not stated centrally.

**Future.**

- Add an explicit *"no emoji in LLM output"* rule to every prompt. PLANNED.
- Lint-style validation that LLM output meets the required heading set
  (catch missing sections before render). PLANNED — see §20.
- Central style-guide file in repo for prompt authors. PLANNED.

### 2.3 Communication Principles — *Applicable*

#### Principles enforced by prompts (in code today)

- **Honesty over fluency.** *"If the answer is not supported by the
  context, say so plainly and suggest what information would be needed."*
  — `prompts/anomaly_chat_prompt.txt`. The chat agent never invents
  columns or invoice IDs.
- **Epistemic humility.** *"If the question is outside this scope, say
  so."* — `prompts/status_prompt.txt`.
- **Pushback on invalid input.** The chat FSM responds to a malformed
  date with *"I couldn't read that date range"* plus an example, instead
  of guessing (`backend/main.py::_handle_await_dates` →
  `validate_date_range`).
- **Confirmation before side effects.** The agent never writes to
  `anomaly_metadata` or triggers Airflow on the first turn — it parses,
  echoes the parsed range, and waits for `confirm`
  (`backend/main.py::_handle_confirm`).

#### Failure-mode behaviour (in code today)

| Failure | What the user sees |
|---------|--------------------|
| LLM unreachable / quota exhausted | Each `llm_service.py` function has a deterministic fallback (regex, plain-table, static summary). The narrative degrades; the page does not crash. |
| LLM returns malformed JSON | Strip ```json fences, try `json.loads`, log a warning, drop the chunk. Remaining chunks continue. |
| Airflow SSH fails | Metadata is already written; assistant says *"Metadata was written but the Airflow trigger failed"* with `stderr` in a fenced block, and instructs the user to reply `retry`. |
| DB unreachable | `/api/health` flips `db: "down"`; the header badge in `App.jsx` turns amber. |

**Future.**

- Confidence scoring on anomalies (separate dimension from `severity`).
  Today only `severity` (low/medium/high) is emitted. PLANNED — §5, §17.
- Refusal templates for out-of-scope questions. The chat prompt
  instructs the model to say so, but there is no canonical refusal
  template. PLANNED.

### 2.4 Brand Alignment — *Applicable*

#### Visual & UX parity with AdminFee Agent (in code today)

- Same 3-panel layout: chat (left) / status monitor (centre) / analyst
  (right). `frontend/src/App.jsx` mirrors AdminFee's `App.jsx` structure.
- Same header treatment: brand dot + product name + tagline + health
  badge + *New Session* button (`frontend/src/index.css` `.app-header`).
- Same monospace status chips for FSM steps (`.step-chip` with per-state
  colour variants).
- Same dark theme via CSS variables in `:root` (`--bg`, `--accent`,
  `--ok`, `--warn`, `--err`) so a switch to the AdminFee theme is one
  variable change.
- Same step-based FSM in the backend; AdminFee Agent uses the same
  `session_manager` pattern (UUID dict, `threading.Lock`).

#### Brand voice continuity (in code today)

- Both agents introduce themselves with the product name in **bold** and
  ask for one concrete input before doing anything.
- Both products use markdown reports with required section headings to
  make outputs scannable for auditors.
- Both products surface backend health in the header so the operator
  can tell at a glance whether the LLM/DB are reachable.

**Future.**

- Shared component library / design-tokens package between the two
  apps. Today the patterns are duplicated between repos. PLANNED.
- Brand kit (logo, colour palette, typography spec) in repo. The
  `brand-dot` is a CSS pseudo-element today; no actual logo asset
  exists. PLANNED.
- Light-theme + theme switcher. Variables are dark-only today; the
  `var(...)` structure already supports a sibling
  `[data-theme="light"]` block. PLANNED.
- Internationalisation (i18n) of UI strings. PLANNED.

### 2.5 Example Interactions — *Applicable*

Each transcript below is a literal output of code on this branch.
Assistant turns come from `backend/main.py` + `prompts/*`; user turns
are exactly what the analyst types in the chat panel.

#### Example 1 — Happy path: greeting → confirm → trigger

```text
AGENT: Hello — welcome to the **Anomaly Detection Agent**.
Please provide a date range (e.g. `2024-12-25 to 2025-12-25`) or type `exit` to quit.

USER: 2024-01-01 to 2024-12-31

AGENT: I parsed:

- **Start date:** `2024-01-01`
- **End date:** `2024-12-31`

Reply `confirm` to run the anomaly pipeline or send a new range.

USER: confirm

AGENT: ✅ Anomaly pipeline triggered.

- **Run ID:** `anomaly_20260101_143012`
- **Range:** `2024-01-01` → `2024-12-31`

Watch the **Status Monitor** panel for progress.
```

#### Example 2 — Pushback on invalid input

```text
USER: last quarter sometime

AGENT: I couldn't read that date range (Missing start or end date).
Please try again, e.g. `2024-01-01 to 2024-12-31`.
```

When the LLM cannot extract dates, the regex fallback in
`backend/llm_service.py::_normalize_with_regex` returns `(None, None)`;
`validate_date_range` flags it; the agent does not guess.

#### Example 3 — Soft failure of the Airflow trigger

```text
USER: confirm

AGENT: ⚠️ Metadata was written but the Airflow trigger failed:

​```
ssh: connect to host 172.31.25.132 port 22: Connection timed out
​```

Fix the SSH / DAG configuration and reply `retry`.
```

#### Example 4 — Analyst follow-up Q&A (with optional SQL)

```text
USER (analyst panel): Which vendor has the most duplicates?

AGENT: Vendor `ACME Logistics` accounts for 6 of the 17 detected
duplicates, all in the `2024-Q3` window. Two of those (`INV-1042`,
`INV-1071`) are exact-amount near-duplicates separated by 2 days; the
other four are split-payment patterns under the `vendor_alias` value
`ACME LOG.`

[expandable: Generated SQL]
SELECT vendor_name, COUNT(*) AS duplicate_count
FROM anomaly.duplicate_ap_invoice
GROUP BY vendor_name
ORDER BY duplicate_count DESC
LIMIT 200
```

The natural-language answer is produced by `chat_about_anomalies`
(`prompts/anomaly_chat_prompt.txt`). The SQL leg is opportunistic —
`generate_sql` + `database.run_select_safely`; if `generate_sql` returns
empty or the SQL is rejected, the answer still renders without the
expandable block.

#### Example 5 — Status Q&A from the centre panel

```text
USER: How many high-severity anomalies are there?

AGENT: There are 4 high-severity anomalies in the current run
(out of 17 total). The latest update was at 14:31 UTC.
```

**Future.**

- Persistent transcripts across sessions / replay. Today
  `Session.history` is in-process only; lost on backend restart.
  PLANNED — roadmap Phase 1.
- These five examples become "gold-standard" eval fixtures, not just
  documentation. PLANNED — §20.2.

---

# Part II — Architecture & Models

## 3. System Architecture Overview

### 3.1 High-Level Diagram — *Applicable*

**In code today.**

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

The blocks above all exist on this branch. The arrows represent live
transports (HTTP, MySQL wire, SSH, HTTPS to OpenAI).

**Future additions to this diagram (not in code today).**

- Persistent session store (Postgres or Redis) replacing the in-process
  `SessionStore`. PLANNED — roadmap Phase 1.
- Airflow REST polling loop so the chat panel can report SUCCESS /
  FAILED. PLANNED — roadmap Phase 2.
- SSE / WebSocket channel for push updates (replaces or supplements
  the 30-second poll). PLANNED — roadmap Phase 3 + §14.
- Optional S3 ingestion path. PLANNED — `boto3` is pinned but no S3
  code path is active.

### 3.2 Component Inventory — *Applicable*

#### Backend (in code today)

| Module | Responsibility |
|--------|----------------|
| `backend/main.py` | FastAPI app; all 11 route handlers; FSM step handlers (`_handle_await_dates`, `_handle_confirm`, `_trigger_pipeline`); CORS + logging setup. |
| `backend/session_manager.py` | `Session` dataclass, `SessionStore` (UUID-keyed dict, `threading.Lock`), audit log helpers. |
| `backend/llm_service.py` | LLM wrapper: `normalize_date_range`, `understand_dataset`, `detect_anomalies`, `format_report`, `chat_about_anomalies`, `status_qa`, `generate_sql`, `reconciliation_report` — each with a deterministic fallback. |
| `backend/database.py` | SQLAlchemy 2 engine (lazy, `pool_pre_ping`); helpers for `anomaly_metadata`, `anomaly.duplicate_ap_invoice`, `table_column_info`; `run_select_safely` (read-only SQL guard). |
| `backend/airflow_trigger.py` | Paramiko SSH wrapper that runs the Airflow CLI on the EC2 host and returns a `TriggerResult`. |
| `backend/config.py` | `.env` loader; constants for table names, SSH key path, model name. |
| `prompts/*.txt` | Eight prompt templates (date_extract, understanding, anomaly, anomaly_format, anomaly_chat, status, sql, reconciliation). |
| `run_backend.py` | Entrypoint that starts uvicorn with `--reload` watching `backend/` and `prompts/`. |

#### Frontend (in code today)

| File | Responsibility |
|------|----------------|
| `frontend/src/App.jsx` | Root component; 3-panel layout; shared state (`activeDelivery`, `activeContracts`, `processingComplete`); *New Session* reset via `key` prop. |
| `frontend/src/panels/AgentChatPanel.jsx` | Step-based chat UI; calls `/api/agent/start` on mount, posts to `/api/agent/chat`; renders FSM step chip + quick-reply buttons. |
| `frontend/src/panels/StatusMonitorPanel.jsx` | 30-second polling of `/api/status/summary` and `/api/status/contracts`; ref-gated `onProcessingComplete`; status Q&A. |
| `frontend/src/panels/AnalysisPanel.jsx` | Delivery picker; `/api/analysis/setup`; auto-fires `/api/reports/reconciliation`; follow-up Q&A with collapsible SQL + rows. |
| `frontend/src/components/MarkdownRenderer.jsx` | Hand-rolled markdown renderer (HTML-escaped). |
| `frontend/src/services/api.js` | Centralised `fetch` wrapper for every backend call. |
| `frontend/src/index.css` | All styles; CSS variables for the dark theme; responsive breakpoints. |
| `frontend/vite.config.js` | Dev server on `:3000`; `/api` proxy to `:8000`. |

#### External services (in code today)

| Service | Used by | Purpose |
|---------|---------|---------|
| MySQL on AWS RDS (`joblog_metadata`, `anomaly`) | `backend/database.py` | Source of truth for `anomaly_metadata`, `anomaly.duplicate_ap_invoice`, `table_column_info`. |
| Airflow on Ubuntu EC2 | `backend/airflow_trigger.py` (Paramiko SSH) | Runs the anomaly DAG (`AIRFLOW_CMD` env). Fire-and-forget today. |
| OpenAI Chat API | `backend/llm_service.py` (LangChain-OpenAI) | LLM inference for date extraction, anomaly detection, narrative reports, Q&A. |

**Future components (not in code today).**

- Persistence service for sessions and audit (Postgres / Redis). PLANNED.
- Token / cost telemetry sidecar. PLANNED — §22.
- Object storage (S3) for raw invoice ingestion. PLANNED.
- Auth provider (OIDC / Azure AD). PLANNED — §16, roadmap Phase 5.

### 3.3 Request Lifecycle — *Applicable*

**In code today.** End-to-end trace from "open the page" to "anomaly
report displayed":

1. **Page load.** Browser fetches `index.html` from Vite (`:3000`).
   `App.jsx` mounts; the health check fires
   (`GET /api/health` via the `/api` proxy → `:8000`); the header badge
   reads `db: "ok"` (`backend/main.py::health`).
2. **Session start.** `AgentChatPanel` calls `POST /api/agent/start`.
   `SessionStore.create()` allocates a UUID; FSM step is set to
   `await_dates`; the greeting is appended to `Session.history` and
   returned.
3. **Date entry.** User types `"2024-01-01 to 2024-12-31"`.
   `POST /api/agent/chat` runs `_handle_await_dates`:
   - `normalize_date_range` calls the LLM via
     `prompts/date_extract_prompt.txt`. If the LLM fails or returns bad
     JSON, `_normalize_with_regex` parses the dates instead.
   - `validate_date_range` confirms ISO format and `start <= end`.
   - FSM transitions to `confirm`. The reply echoes the parsed range.
4. **Confirmation.** User clicks *Confirm & run*. `_handle_confirm`
   calls `_trigger_pipeline`:
   - `database.upsert_anomaly_metadata` truncates and inserts into
     `anomaly_metadata`. Audit event `metadata_written`.
   - `airflow_trigger.trigger_airflow_dag(run_id)` opens an SSH
     connection (Paramiko, `AutoAddPolicy`, `SSH_KEY_PATH`), runs
     `AIRFLOW_CMD --run-id <run_id>`, captures stdout/stderr/exit
     status.
   - On success, FSM transitions to `done`; on failure, to `error` with
     stderr surfaced to the user. Audit event `airflow_trigger`.
5. **Completion detection.** `StatusMonitorPanel` polls every 30 s
   (`POLL_MS = 30_000`). `/api/status/summary` maps the FSM step to
   `processing_state` (`done` → `complete`). The
   `processingStartedRef` and `completionFiredRef` guards ensure
   `onProcessingComplete(contracts)` fires exactly once per run.
6. **Auto analysis.** `App.jsx` flips `processingComplete` to `true`.
   `AnalysisPanel`'s `autoFiredRef` calls `runSetup`, which posts to
   `/api/analysis/setup`:
   - `database.fetch_anomaly_data()` and `fetch_column_metadata()` load
     rows + column comments.
   - `llm_service.understand_dataset` runs
     `prompts/understanding_prompt.txt`.
   - `llm_service.detect_anomalies` runs
     `prompts/anomaly_prompt.txt` once per 200-row chunk; results are
     deduped on `invoice_id`.
   - `llm_service.format_report` runs
     `prompts/anomaly_format_prompt.txt`.
   - The result is cached on `Session.analysis`.
7. **Auto reconciliation.** `AnalysisPanel.fireReconciliation` posts to
   `/api/reports/reconciliation` with the same `session_id`.
   `llm_service.reconciliation_report` runs
   `prompts/reconciliation_prompt.txt`; the markdown report is
   returned and rendered.
8. **Follow-up Q&A.** User types a question. `POST /api/analysis/ask`
   runs `chat_about_anomalies` for the natural-language answer, then
   *opportunistically* runs `generate_sql` + `database.run_select_safely`.
   If the SQL succeeds, rows ride along in the response and render
   inside a collapsible `<details>` block.

**Future changes to the lifecycle.**

- Step 5 should ideally be Airflow-driven (real run state) rather than
  FSM-derived. PLANNED — roadmap Phase 2.
- Step 6's blocking LLM calls should stream tokens to the UI. PLANNED
  — §14.
- Step 8's SQL execution should be sandboxed to a read-replica. PLANNED.

### 3.4 Technology Stack — *Applicable*

#### Pinned versions (in code today)

**Backend** — `backend/requirements.txt`:

| Package | Version | Role |
|---------|---------|------|
| `fastapi` | 0.115.5 | HTTP framework + OpenAPI |
| `uvicorn[standard]` | 0.30.6 | ASGI server (`--reload`) |
| `pydantic` | 2.9.2 | Request / response models |
| `python-dotenv` | 1.0.1 | `.env` loader |
| `sqlalchemy` | 2.0.36 | DB engine + Core |
| `pymysql` | 1.1.1 | MySQL driver |
| `langchain-openai` | 0.2.9 | `ChatOpenAI` wrapper |
| `langchain-core` | 0.3.21 | LangChain primitives |
| `openai` | 1.55.0 | Pinned transitively for LangChain |
| `boto3` | 1.35.63 | S3 client (pinned, not yet used) |
| `paramiko` | 3.4.1 | SSH client for Airflow trigger |
| `pandas` | 2.2.3 | Tabular helpers |
| `openpyxl` | 3.1.5 | Excel I/O (pinned, light use) |
| `cryptography` | 43.0.3 | Fernet (pinned, not yet used) |
| `python-multipart` | 0.0.12 | Multipart form parsing |

**Frontend** — `frontend/package.json`:

| Package | Version | Role |
|---------|---------|------|
| `react` | ^18.3.1 | UI runtime |
| `react-dom` | ^18.3.1 | Browser renderer |
| `vite` | ^5.4.11 | Dev server + bundler |
| `@vitejs/plugin-react` | ^4.3.4 | Fast Refresh + JSX |

**Languages.** Python 3.11+ (typed `from __future__ import annotations`,
`type | None` syntax); plain JavaScript (no TypeScript) on the frontend;
plain CSS (no Tailwind, no CSS-in-JS).

**Runtime.** Local dev only. uvicorn on `:8000` (`backend/run_backend.py`);
Vite on `:3000` (`frontend/vite.config.js`) with a `/api` proxy.

**Future stack additions (not in code today).**

- TypeScript on the frontend. PLANNED.
- Pytest + Vitest test runners. PLANNED — §20.
- Docker + gunicorn for prod. PLANNED — roadmap Phase 6.
- Anthropic / Bedrock / Ollama provider behind `get_llm`. PLANNED — §5.

### 3.5 Key Architectural Decisions — *Applicable*

ADR-style summary of the major trade-offs already made in the code,
each with the alternative considered and why it was not chosen.

#### ADR-1 — Hand-rolled FSM in Python, not LangGraph

- **Decision.** The chat panel is driven by a plain dict-based FSM in
  `backend/session_manager.py` + `backend/main.py::_handle_*`.
- **Alternative.** Use LangGraph (as the legacy
  `anomaly_processing_agent.py` does).
- **Why this way.** The web UI needs one HTTP call per FSM transition;
  LangGraph's compiled graph adds plumbing (state dataclasses, node
  registration) without a payoff at this size. The legacy LangGraph
  scripts are preserved at the repo root for reference but are not
  imported by the FastAPI backend.

#### ADR-2 — Polling, not push, for status

- **Decision.** `StatusMonitorPanel` polls every 30 s.
- **Alternative.** Server-Sent Events or WebSockets.
- **Why this way.** Polling works behind every corporate proxy and
  needs zero infrastructure. The cost is up-to-30-second lag, which is
  acceptable for a multi-minute Airflow run. SSE is on the roadmap
  (§14).

#### ADR-3 — In-memory session store

- **Decision.** `SessionStore` is a `dict` keyed by UUID, guarded by a
  `threading.Lock`.
- **Alternative.** Postgres / Redis from day one.
- **Why this way.** Acceptable for an MVP run on one developer laptop;
  zero ops cost; the interface is small enough that swapping to a
  persistent backend is a one-class change. Tracked in §1.3 / §11 /
  roadmap Phase 1.

#### ADR-4 — Regex / deterministic fallback for every LLM call

- **Decision.** Every public function in `backend/llm_service.py` has a
  non-LLM fallback (`_normalize_with_regex`, plain markdown table,
  static reconciliation summary).
- **Alternative.** Surface an error to the user when the LLM fails.
- **Why this way.** LLM outages, quota exhaustion, and model
  hallucinations should degrade the narrative — not crash the page.
  The auditor still gets a usable view (regex-extracted dates,
  plain-table report) and can retry later.

#### ADR-5 — Read-only SQL execution path for analyst Q&A

- **Decision.** `/api/analysis/ask` may execute LLM-generated SQL via
  `database.run_select_safely`, which rejects any non-`SELECT` and
  destructive verbs.
- **Alternative.** Never execute LLM-generated SQL; only show it.
- **Why this way.** Showing the SQL plus its result rows lets the
  auditor verify an LLM claim. The guard ensures a malicious or
  hallucinated statement cannot mutate data.

#### ADR-6 — No third-party UI library

- **Decision.** Plain CSS (`frontend/src/index.css`) + a hand-rolled
  markdown renderer (`MarkdownRenderer.jsx`).
- **Alternative.** MUI / Chakra / Ant Design + `react-markdown`.
- **Why this way.** Keeps the bundle small, dependency surface minimal,
  and matches the AdminFee Agent codebase. The markdown renderer is
  ~200 LOC and supports every construct the prompts emit.

#### ADR-7 — No auth / no multi-tenant on this branch

- **Decision.** Single-tenant, anonymous `session_id`, CORS locked to
  `localhost`.
- **Alternative.** Wire OIDC / RBAC up front.
- **Why this way.** Premature for an MVP that one operator runs locally.
  Documented as a non-goal (§1.4) and a Phase 5 roadmap item.

**Future ADRs not yet written (PLANNED).**

- ADR-8 Persistent session backend.
- ADR-9 Airflow REST polling and status push.
- ADR-10 LLM streaming over SSE.
- ADR-11 Multi-domain anomaly support.
- ADR-12 Auth + RBAC.

---

## 4. Multi-Agent Topology & Roles

> **Section orientation.** The Anomaly Agent is a *single-agent* system
> driven by a hand-rolled FSM (see ADR-1 in §3.5). It does not have a
> multi-agent topology, supervisor router, or inter-agent handoff. Most
> subsections of this LLD chapter are therefore **NA**. The two that
> have a meaningful analogue — *logical LLM roles* and *concurrency /
> scaling rules for the one agent we do have* — are filled in below.

### 4.1 Agent Roster — *Applicable (loose interpretation)*

**In code today.** There is exactly one *agent* in the architectural
sense: the FastAPI session, which owns the FSM, the audit log, and the
analysis cache (`backend/session_manager.Session`). What the LLD
template calls a "specialised agent" maps in this codebase to a
**logical LLM role** — a distinct prompt + caller pair invoked by the
single backend agent.

There are eight such logical roles, all backed by `backend/llm_service.py`
and prompts under `prompts/`:

| Logical role | Caller (backend) | Prompt file | Inputs | Output | Where used |
|--------------|------------------|-------------|--------|--------|------------|
| Date extractor | `normalize_date_range` | `date_extract_prompt.txt` | Free-text date range from the chat panel | JSON `{start_date, end_date}` | `_handle_await_dates` (chat FSM) |
| Dataset summariser | `understand_dataset` | `understanding_prompt.txt` | First 200 rows of `duplicate_ap_invoice` + column metadata | Markdown narrative ≤ 180 words | `/api/analysis/setup` |
| Anomaly detector | `detect_anomalies` | `anomaly_prompt.txt` | One 200-row chunk + understanding + memory + columns | JSON array of anomaly objects | `/api/analysis/setup` (looped per chunk) |
| Report formatter | `format_report` | `anomaly_format_prompt.txt` | Deduped anomaly list | Markdown report with 4 fixed sections | `/api/analysis/setup` |
| Analyst chatbot | `chat_about_anomalies` | `anomaly_chat_prompt.txt` | Question + anomalies + understanding + columns | 2–6 sentence markdown answer | `/api/analysis/ask` |
| Status assistant | `status_qa` | `status_prompt.txt` | Question + summary + 50-row sample | 1–4 sentence markdown answer | `/api/status/ask` |
| SQL generator | `generate_sql` | `sql_prompt.txt` | Question + column metadata + table FQN | Single MySQL `SELECT` (fenced) | `/api/analysis/ask` (opportunistic) |
| Reconciler | `reconciliation_report` | `reconciliation_prompt.txt` | Date range + summary + anomalies sample | Markdown report with 5 fixed sections | `/api/reports/reconciliation` |

All eight roles share a single `ChatOpenAI` client constructed once in
`get_llm()`; there is no per-role model selection, no per-role API key,
and no separate process per role.

**Future.**

- Promote one or more of these roles to a true **separate agent** — for
  example, an evaluator agent that judges the anomaly detector's output
  before the auditor ever sees it. PLANNED — §17 + §20.2.
- Per-role model routing (cheap model for date extraction, premium
  model for analyst Q&A). PLANNED — §5.2.
- A *planner* agent that decomposes a complex auditor question into a
  pipeline of role calls. PLANNED — §10.2.

### 4.2 Coordination Pattern — *NA*

**Why NA.** The architecture has no supervisor, router, swarm, or
hierarchical pattern to choose between. There is exactly one agent (the
FastAPI session); coordination happens through:

- A finite state machine inside the agent
  (`STEP_GREET → STEP_AWAIT_DATES → STEP_CONFIRM → STEP_PROCESSING →
  STEP_DONE | STEP_ERROR`, defined in `backend/session_manager.py`).
- Three parallel UI panels in the browser that call distinct backend
  routes; the panels do not negotiate with each other — they read
  shared state held in `App.jsx`.

Neither of those is "multi-agent coordination" in the sense the LLD
template means.

**Future.** A coordinator pattern will become applicable if one of the
PLANNED items in §4.1 lands (e.g. an evaluator agent that runs after
the anomaly detector). At that point this subsection should be
re-labelled *Applicable* and a topology written.

### 4.3 Handoff Protocol — *NA*

**Why NA.** There are no agent-to-agent handoffs because there is only
one agent. The closest analogue is the **panel-to-panel propagation**
mediated by `App.jsx`:

- `AgentChatPanel` → `App` via `onRangeSelected({start_date, end_date})`,
  which sets `activeDelivery`.
- `StatusMonitorPanel` → `App` via `onProcessingComplete(contracts)`,
  which sets `processingComplete = true`.
- `App` → `AnalysisPanel` via the `processingComplete` prop, which
  triggers `autoFiredRef`-gated `runSetup`.

That is *intra-frontend state propagation*, not a handoff protocol
between agents. Documented for completeness only.

**Future.** A handoff protocol will be needed if a second agent is
introduced (PLANNED, §4.1). Likely shape: a structured "trace"
attached to the `Session`, with each agent appending a typed step.

### 4.4 Conflict Resolution — *NA*

**Why NA.** With one agent there is no possibility of two agents
disagreeing or producing contradictory outputs. Within the single
agent, the closest concept is **deduplication** of LLM output across
chunks:

- `detect_anomalies` runs the LLM once per 200-row chunk; results are
  merged and deduped on `invoice_id` so the same record cannot appear
  twice (`backend/llm_service.py`):

```python
unique = {a.get("invoice_id") or a.get("id") or json.dumps(a, sort_keys=True, default=str): a for a in all_anomalies}
return list(unique.values())
```

That is consistency enforcement, not conflict arbitration.

**Future.** Conflict resolution becomes meaningful only if a second
agent (e.g. evaluator) can disagree with the anomaly detector. PLANNED
— §17.

### 4.5 Scaling Rules — *Applicable*

The "scaling" question for this app is *how the single agent handles
many input rows*, not how many agent instances to spawn.

**In code today.**

- **Sequential chunking.** `detect_anomalies` iterates over 200-row
  chunks, invoking the LLM once per chunk. Chunk size constant:
  `chunk_size: int = 200` in `backend/llm_service.py`. No parallelism;
  chunks are processed in source order.
- **Single concurrent session per backend process.** `SessionStore` is
  thread-safe (one `threading.Lock`) and supports many sessions
  simultaneously, but uvicorn is started with default worker count
  (`reload=True` implies one worker), so practical parallelism is one.
- **Single-row metadata table.** `anomaly_metadata` is truncated and
  re-inserted on every confirm (`upsert_anomaly_metadata`); two
  concurrent runs would race. Mitigated today by single-operator
  assumption.

**Future.**

- **Parallelise anomaly chunks** with `asyncio.gather` or a thread
  pool. Constraints: per-OpenAI-key rate limit; preserve dedup on
  `invoice_id` so order does not matter. PLANNED.
- **Multi-worker uvicorn / gunicorn** for prod. Requires a persistent
  session store first (in-memory dict cannot span workers). PLANNED —
  roadmap Phase 1 + Phase 6.
- **Multi-row metadata table** keyed by `run_id` so concurrent runs do
  not race. PLANNED — roadmap Phase 2.
- **Spawn-parallel agents** rule: if the evaluator agent (PLANNED,
  §4.1) is added, run it in parallel with the report formatter on the
  same anomaly list, since their inputs do not depend on each other.
  PLANNED.

---

## 5. LLM Strategy & Model Selection

> **Section orientation.** The Anomaly Agent uses a single LLM
> (OpenAI `gpt-4.1-mini`) for every logical role listed in §4.1. There
> is no fallback model, no routing logic, and no fine-tuning on this
> branch. §5.1 and §5.3 are *Applicable*; §5.2, §5.4, §5.5 are **NA**
> today, with the future conditions under which each would become
> applicable.

### 5.1 Model Portfolio — *Applicable*

#### In code today

A single-row portfolio. The model is constructed once on first call in
`backend/llm_service.py::get_llm` and memoised:

```python
_llm = ChatOpenAI(model=OPENAI_MODEL, temperature=OPENAI_TEMPERATURE)
```

| Slot | Model | Provider | Env override | Notes |
|------|-------|----------|--------------|-------|
| Primary | `gpt-4.1-mini` | OpenAI | `OPENAI_MODEL` (`backend/config.py`) | Used by every logical role in §4.1. |
| Temperature | `0` | — | `OPENAI_TEMPERATURE` (`backend/config.py`) | Deterministic. JSON-emitting prompts (date_extract, anomaly) rely on this. |
| Fallback model | *none* | — | — | If the LLM is unreachable, every `llm_service.py` function falls back to a *deterministic* path (regex / plain-table / static summary), not to a second model. See ADR-4 in §3.5. |

The legacy scripts at the repo root (`anomaly_processing_agent.py`,
`anomaly_analyst.py`) contain commented-out `ChatOllama` configuration
for a local Llama 3.1 model. **That code path is not active in the
FastAPI backend** — no Ollama call happens on this branch.

#### Cost / latency / quality trade-offs (informal)

| Dimension | Today |
|-----------|-------|
| Cost | Mini-tier OpenAI pricing on every call. No token tracking yet (§22). |
| Latency | Blocking `.invoke(prompt)` per call. Median end-to-end for `/api/analysis/setup` is dominated by the chunked `detect_anomalies` loop (one round-trip per 200-row chunk). |
| Quality | Adequate for the task per spot-checks; not formally evaluated (§5.5). |

#### Future

- **Add a fallback model.** Today a 5xx from OpenAI degrades the
  narrative to a regex / static fallback. A fallback to Anthropic
  Claude or Bedrock Claude would preserve the LLM-quality narrative
  during an OpenAI outage. PLANNED.
- **Add a premium tier for Q&A.** Use `gpt-4.1` (or Claude Sonnet) for
  `chat_about_anomalies` and `reconciliation_report` while keeping
  `gpt-4.1-mini` for date extraction. PLANNED — see §5.2.
- **Add an embedding model** (when RAG becomes applicable; see §9).
  PLANNED.

### 5.2 Routing Logic — *NA*

**Why NA.** Every logical role in §4.1 calls the *same* `ChatOpenAI`
instance. There is no per-task complexity heuristic, no per-user-tier
routing, no fall-back-on-low-confidence policy. Routing is a property
of a portfolio with more than one entry; the Anomaly Agent has one
entry today.

**Future conditions for this subsection becoming Applicable.**

- A second model lands in §5.1 (premium tier or fallback). At that
  point a routing rule per logical role is straightforward — extend
  `get_llm` to accept a `role` argument and look it up in a small
  dict. PLANNED.
- A "model cascade" pattern (cheap-first, escalate on low confidence)
  becomes desirable. Same hook point. PLANNED — §22.4.

### 5.3 Provider Abstraction — *Applicable*

**In code today.** The abstraction is **deliberately thin**: one
function returning one client.

```python
# backend/llm_service.py
def get_llm() -> ChatOpenAI:
    global _llm
    if _llm is None:
        _llm = ChatOpenAI(model=OPENAI_MODEL, temperature=OPENAI_TEMPERATURE)
    return _llm
```

```python
# every public function uses the same envelope
def invoke_llm(prompt: str) -> str:
    try:
        resp = get_llm().invoke(prompt)
        return (resp.content or "").strip()
    except Exception as exc:
        log.exception("LLM invocation failed: %s", exc)
        return ""
```

What this gives us today:

| Property | Notes |
|----------|-------|
| Model swap via env | `OPENAI_MODEL=gpt-4o-mini python run_backend.py` works without code changes — anything `ChatOpenAI` accepts. |
| Temperature swap via env | Same; `OPENAI_TEMPERATURE=0.4` if a creative role is added later. |
| Vendor swap | Limited. `ChatOpenAI` is OpenAI-specific (LangChain class). Switching to Anthropic / Bedrock requires importing a sibling LangChain class and changing the construction line. |
| Graceful failure | `invoke_llm` swallows every exception, logs with `log.exception`, and returns `""`. Each caller's deterministic fallback handles the empty string. |

#### Future

- **True multi-provider abstraction.** Replace the `ChatOpenAI`
  reference with a `BaseChatModel` and select the concrete subclass
  via env (`LLM_PROVIDER=openai|anthropic|bedrock|ollama`). LangChain
  already exposes the parent class; the change is small but PLANNED.
- **Native SDK option.** For prompt-caching (Anthropic) or batch
  inference, switch directly to the `anthropic` / `openai` SDK instead
  of LangChain. PLANNED.
- **Streaming.** `invoke_llm` is blocking. Adding a `stream_llm`
  variant that yields tokens belongs here. PLANNED — §14.2.

### 5.4 Fine-Tuning & Adaptation — *NA*

**Why NA.** No fine-tuning, LoRA, or model adaptation is performed for
the Anomaly Agent. Every behavioural specialisation lives in:

- The eight prompt files under `prompts/` (§6, §4.1).
- The deterministic fallbacks in `backend/llm_service.py`.

No training data is collected, no model artefacts are stored, no
inference happens against a custom checkpoint.

**Future conditions for this subsection becoming Applicable.**

- The auditor feedback loop (PLANNED, §19.4) starts collecting
  thumbs-up/thumbs-down labels on individual anomalies. With enough
  labels, supervised fine-tuning of the anomaly detector role becomes
  worth considering. PLANNED.
- A domain-specific embedding model is needed for RAG (§9). PLANNED.

### 5.5 Evaluation & Swap Criteria — *NA*

**Why NA.** There is no automated evaluation harness on this branch:

- No golden-set fixtures.
- No rubric-based grading.
- No LLM-as-judge harness.
- No regression suite that pins the output of any prompt.
- No threshold for "model X has improved enough to swap in."

The only check today is the spot-checking the developer does while
running the app locally.

**Future.** The eval surface that should exist before any model swap is
attempted is described in §20.2:

- A `tests/eval/` fixture set: hand-curated `(input, expected)` pairs
  for each logical role in §4.1.
- A nightly LLM-as-judge run that scores responses against the rubric
  in each prompt's required-headings contract (anomaly_format_prompt:
  4 headings; reconciliation_prompt: 5 headings).
- Swap criteria: a candidate model must (a) match or beat the current
  model on the rubric, (b) be cheaper or comparable per call, (c)
  preserve the JSON-emitting roles' parse rate (date_extract,
  anomaly_prompt). PLANNED.

---

# Part III — Behavior & Knowledge

## 6. Prompt Engineering & System Prompts

### 6.1 System Prompt Structure — *Applicable*

**In code today.** The Anomaly Agent does not use a single global
system prompt. Instead, each of the eight logical roles in §4.1 has its
own prompt file under `prompts/`, and each follows the same
canonical layout:

1. **Role line.** Opens with *"You are ..."* establishing the persona
   for that role (e.g. *"You are an anomaly detection engine for an
   Accounts Payable duplicate invoice dataset."*).
2. **Output contract.** What the LLM must emit (JSON shape, markdown
   sections, length cap).
3. **Rules block.** Numbered or bulleted list of hard constraints
   ("Do NOT include commentary", "Use ONLY columns from the metadata",
   "JSON ARRAY only, no fences").
4. **Context placeholders.** `str.format` placeholders such as
   `{column_info}`, `{understanding}`, `{anomalies}`.
5. **Footer marker.** Trailing label such as `JSON:` or `ANSWER:` to
   nudge the model into the expected output mode.

Example skeleton (`prompts/anomaly_chat_prompt.txt`):

```
You are the Anomaly Agent's analyst chatbot. ...

Answer using ONLY the context below. ...

Style:
- Direct, 2–6 sentences.
- Cite specific invoice_id values when relevant.
- ...

COLUMN METADATA: {column_info}
DATASET UNDERSTANDING: {understanding}
DETECTED ANOMALIES (JSON): {anomalies}
USER QUESTION: {question}

ANSWER:
```

**Future.**

- Promote shared rules ("never invent fields", "no emoji in LLM
  output") into a tiny shared header that every prompt prepends, so
  edits stay DRY. PLANNED.
- Add an explicit `<persona>`, `<rules>`, `<context>`, `<task>` XML
  scaffold (Anthropic-style) for prompts that move to Claude when §5.1
  expands. PLANNED.

### 6.2 Prompt Templates & Variables — *Applicable*

**In code today.** Prompts are loaded from disk on first use and cached
in process memory:

```python
# backend/llm_service.py
_prompt_cache: dict[str, str] = {}

def load_prompt(name: str) -> str:
    if name not in _prompt_cache:
        path: Path = PROMPTS_DIR / f"{name}.txt"
        _prompt_cache[name] = path.read_text(encoding="utf-8")
    return _prompt_cache[name]
```

Variables are injected with `str.format(**kwargs)`. Literal `{` / `}`
characters must be doubled (`{{` / `}}`). Today only
`prompts/date_extract_prompt.txt` exercises this — it includes a JSON
skeleton `{{"start_date": "...", "end_date": "..."}}`.

| Prompt file | Required placeholders |
|-------------|------------------------|
| `date_extract_prompt.txt` | `{input}` |
| `understanding_prompt.txt` | `{column_info}`, `{data}` |
| `anomaly_prompt.txt` | `{column_info}`, `{understanding}`, `{memory}`, `{data}` |
| `anomaly_format_prompt.txt` | `{anomalies}` |
| `anomaly_chat_prompt.txt` | `{column_info}`, `{understanding}`, `{anomalies}`, `{question}` |
| `status_prompt.txt` | `{summary}`, `{rows}`, `{question}` |
| `sql_prompt.txt` | `{column_info}`, `{question}`, `{table}` |
| `reconciliation_prompt.txt` | `{start_date}`, `{end_date}`, `{summary}`, `{anomalies}` |

A missing placeholder raises `KeyError` at runtime — there is no
template-time validation today.

**Future.**

- Schema-validated templates (e.g. Pydantic dataclass per prompt with
  the variable signature) so a `KeyError` becomes a startup failure
  rather than a runtime crash. PLANNED.
- Per-environment prompt overrides via `prompts/<env>/...`. PLANNED.

### 6.3 Few-Shot Example Library — *NA*

**Why NA.** None of the eight prompts include few-shot examples today.
Each prompt is zero-shot: it states the role, the contract, the rules,
and the placeholders, then asks for output. The required-headings
contract in `anomaly_format_prompt.txt` and `reconciliation_prompt.txt`
serves as the structural skeleton in lieu of examples.

**Future conditions for this subsection becoming Applicable.**

- The eval harness in §20.2 produces a curated golden set; the best
  fixtures are promoted into the prompts as few-shot examples.
  PLANNED.
- A token-budget cap (§22.2) forces compression of the rules block
  into examples instead of prose. PLANNED.

### 6.4 Prompt Versioning — *NA*

**Why NA.** Prompts are checked into git with no per-prompt version
tag, no metadata header, and no A/B routing. The git history of
`prompts/*.txt` is the only source of "what changed when". There is no
runtime mechanism to roll back to an older prompt without a code
deploy.

**Future conditions for this subsection becoming Applicable.**

- A `prompts/<name>.v<N>.txt` naming convention with an env-selectable
  default. PLANNED.
- A small `prompt_versions` table that records `(prompt_name, version,
  hash, deployed_at)` so a regression can be tied back to a specific
  prompt change. PLANNED — §21.2.
- Prompt A/B testing tied to a feature-flag layer (§15.4). PLANNED.

### 6.5 Anti-Patterns — *Applicable*

**In code today.** The prompts deliberately avoid known-bad patterns,
and the wrapper code defends against the rest.

| Anti-pattern | How the codebase avoids it |
|--------------|----------------------------|
| Negation overload ("don't do X, don't do Y, never Z, don't W ..."). | Each prompt's "Rules:" block is short — typically 4–6 lines. |
| Conflicting rules. | Required headings (anomaly_format_prompt: 4; reconciliation_prompt: 5) are stated once each. |
| Hidden instructions in user content. | User free-text from the chat panel is never templated as instructions; it is always the value of `{input}`, `{question}`, etc. There is no concatenation of system + user instructions in the same string slot. |
| JSON-with-prose output. | Date extraction and anomaly detection prompts say "JSON only" and the wrapper strips ```json fences with `_strip_json_fences`. |
| Hallucinated columns. | Every prompt that references the data passes the real column metadata explicitly (`{column_info}`); the rules block forbids inventing columns. |
| Destructive SQL via Q&A. | `sql_prompt.txt` instructs the model to add `LIMIT 200` and to never use INSERT/UPDATE/DELETE/DROP/ALTER/TRUNCATE; `database.run_select_safely` re-checks at runtime. |
| Free-form output where structure is needed. | The format / reconciliation prompts pin the heading set; the chat prompt pins sentence count. |
| Empty / null replies passed to the renderer. | `invoke_llm` returns `""` on failure; each caller's deterministic fallback supplies a non-empty string. |

**Future.**

- A static lint pass over `prompts/*.txt` that detects negation overload
  (e.g. > 6 "don't" / "never" lines). PLANNED.
- A runtime check that the LLM output contains all the required
  headings before rendering — see §2.2 future. PLANNED.

---

## 7. Tool Use & Function Calling

### 7.1 Tool Catalog — *Applicable (loose interpretation)*

**Section orientation.** The Anomaly Agent does not use OpenAI / Claude
function-calling today — every prompt returns plain JSON or markdown,
and the backend dispatches actions deterministically based on FSM
state. What the LLD template calls "tools" therefore maps to **the set
of side-effecting backend operations** the FSM may invoke on the user's
behalf.

**In code today.**

| Tool | Caller | Side effect | Cost / latency | Owner |
|------|--------|-------------|----------------|-------|
| `upsert_anomaly_metadata(start_date, end_date)` | `_trigger_pipeline` | Truncates and re-inserts a single row in `anomaly_metadata`. | One round-trip to MySQL. | `backend/database.py` |
| `trigger_airflow_dag(run_id)` | `_trigger_pipeline` | Opens an SSH connection to the EC2 host and runs `AIRFLOW_CMD --run-id <id>`. | Tens of seconds (network + Airflow CLI startup). | `backend/airflow_trigger.py` |
| `fetch_anomaly_data()` | `analysis_setup` | Reads the full `anomaly.duplicate_ap_invoice` table. | Bounded by row count. | `backend/database.py` |
| `fetch_column_metadata(table_name)` | `analysis_setup` | Reads `table_column_info` for column comments. | One small query. | `backend/database.py` |
| `fetch_anomaly_summary()` | `/api/status/summary`, `/api/status/ask` | Counts rows in `anomaly.duplicate_ap_invoice`. | One small query. | `backend/database.py` |
| `fetch_anomaly_rows(limit)` | `/api/status/contracts`, `/api/status/ask` | Reads up to `limit` rows. | One bounded query. | `backend/database.py` |
| `run_select_safely(sql)` | `analysis_ask` (opportunistic) | Executes an LLM-generated `SELECT`. Refuses non-SELECT. | One query. | `backend/database.py` |

Each "tool" has exactly one call site; there is no LLM-driven dispatch
table.

**Future.**

- Promote these to true OpenAI / Claude function-calling tools so a
  more autonomous agent loop (§10.1) can pick which to invoke based on
  the user's question. PLANNED.
- Add a `notify_user(channel, message)` tool for completion alerts.
  PLANNED — §1.2.

### 7.2 Tool Schema Conventions — *Applicable*

**In code today.** Schemas are defined twice:

- **Backend.** Pydantic 2 request / response models in
  `backend/main.py` (e.g. `ChatRequest`, `AnalysisSetupResponse`,
  `StatusSummary`). These are auto-published as JSON Schema at
  `/openapi.json` and rendered by FastAPI's `/docs` page.
- **Frontend.** Plain JavaScript in `frontend/src/services/api.js` —
  no codegen, no shared type package. The frontend trusts the backend
  to return what its OpenAPI spec promises.

| Convention | How it is honoured |
|------------|---------------------|
| Naming | `snake_case` for fields, `kebab/lowercase` for routes (`/api/agent/start`). |
| Parameter design | Path: never; Query: rare (`limit` on `/api/status/contracts`); Body: JSON for every POST. |
| Error shape | `{"detail": "..."}` (FastAPI default). The frontend wrapper raises a JS `Error` whose `.message` is `detail`. |
| Idempotency | Most reads are idempotent; `/api/agent/start` is **not** (creates a new session every call); `/api/agent/chat` is **not** (advances FSM). Documented in `doc/api-reference.md`. |

**Future.**

- TypeScript codegen from the OpenAPI spec into a shared client
  package. PLANNED — §15.2.
- Idempotency keys on the side-effecting routes
  (`/api/agent/start`, `_trigger_pipeline`). PLANNED.

### 7.3 Tool Selection Heuristics — *NA*

**Why NA.** The Anomaly Agent does not let the LLM decide which tool to
call. Tool selection is determined by:

- The FSM step (`STEP_AWAIT_DATES` → date extractor, then validate;
  `STEP_CONFIRM` → metadata write + Airflow trigger).
- The HTTP route (`POST /api/analysis/setup` → fetch + understanding +
  detect + format).

There is no autonomy and therefore no heuristic to document.

**Future.** A heuristic becomes meaningful only after the tools are
exposed as function-calling tools to the LLM (§7.1 future). PLANNED.

### 7.4 Parallel vs. Sequential Execution — *Applicable*

**In code today. All sequential.**

- Within `/api/analysis/setup`: `fetch → understand → detect → format`
  are awaited in series.
- Within `detect_anomalies`: chunks are processed in source order.
- Within `/api/analysis/ask`: natural-language answer first, *then* the
  optional SQL leg — never in parallel.

**Future.**

- Parallelise anomaly chunks (§4.5). PLANNED.
- Run `chat_about_anomalies` and `generate_sql` concurrently in
  `analysis_ask`. PLANNED.
- Pre-fetch `fetch_anomaly_data` and `fetch_column_metadata`
  concurrently in `setup`. PLANNED.

### 7.5 Tool Failure Handling — *Applicable*

**In code today.**

| Tool | Failure surface | Behaviour |
|------|-----------------|-----------|
| `upsert_anomaly_metadata` | DB unreachable | `_trigger_pipeline` catches, sets FSM step to `error`, surfaces the exception to the user. |
| `trigger_airflow_dag` | SSH timeout / auth error / non-zero exit | Returns `TriggerResult(ok=False, stderr=...)`. Assistant echoes `stderr` in a fenced block and instructs the user to reply `retry`. Audit event recorded. |
| `fetch_*` (DB reads) | Most variants log a warning and return `[]` / `0` so the page does not crash. | `fetch_anomaly_summary`, `fetch_anomaly_rows`, `fetch_current_metadata_range` all wrap in `try/except`. |
| `run_select_safely` | Non-SELECT or destructive verb | Raises `ValueError`; `analysis_ask` catches and continues (the natural-language answer still renders). |
| LLM call | Any exception | `invoke_llm` swallows, logs, returns `""`. Each caller's deterministic fallback supplies a non-empty string. |

**Future.**

- Retries with exponential backoff on `trigger_airflow_dag`. Today it
  is one attempt. PLANNED — §26.5.
- Circuit-breaker around the SSH host so a hung host doesn't block
  every chat. PLANNED.
- User-visible toast on tool failure (today the failure is folded into
  the next assistant message). PLANNED.

---

## 8. Memory Architecture

### 8.1 Memory Types — *Applicable*

**In code today.**

| Memory type | Where it lives | Lifetime | Notes |
|-------------|----------------|----------|-------|
| Short-term (single LLM call) | The prompt itself — placeholders are filled at call time. | One round-trip. | No accumulation across calls. |
| Session-scoped chat history | `Session.history: list[ChatTurn]` in `backend/session_manager.py` | Lifetime of the FastAPI process. | Used for display in the chat panel; NOT replayed back into prompts (the FSM-driven prompts re-build their own context every turn). |
| Session-scoped analysis cache | `Session.analysis: dict` (rows, column_info, understanding, anomalies, final_output) | Lifetime of the FastAPI process. | Reused by `/api/analysis/ask`, `/api/reports/reconciliation` to avoid re-running the LLM pipeline. |
| Session-scoped audit | `Session.audit: list[dict]` | Lifetime of the FastAPI process. | Surface: `/api/reports/audit`. |
| Long-term / episodic / semantic | *(none)* | — | The legacy script `anomaly_analyst.py` references a `memory.json` file but the FastAPI backend does not read or write it. |

**Future.**

- **Long-term memory.** Persist `Session.analysis` and confirmed
  anomalies to a `memory` table; feed previously confirmed anomalies
  into `prompts/anomaly_prompt.txt` via the `{memory}` placeholder
  (currently bound to the literal string `"[]"`). PLANNED — roadmap
  Phase 1.
- **Episodic memory.** Per-auditor history of accepted / rejected
  anomalies for personalisation. PLANNED — depends on §16 (auth).
- **Semantic memory.** Vector-indexed natural-language notes that the
  auditor types into the analyst panel. PLANNED — depends on §9 (RAG).

### 8.2 Write Path — *Applicable*

**In code today.**

| Trigger | Writer | Stored as |
|---------|--------|-----------|
| Every chat turn | `Session.add_turn(role, content)` | `Session.history` |
| Every FSM transition / metadata write / airflow trigger | `Session.log(event, detail)` | `Session.audit` |
| `/api/analysis/setup` | `analysis_setup` route | `Session.analysis` (dict) |
| New `Session` | `SessionStore.create()` | `_sessions` dict, keyed by UUID |

There is **no user consent flow** — the auditor's text is captured by
the act of typing it. This is acceptable for an internal MVP but
documented as a posture, not a guarantee. See §1.4 (single-tenant
non-goal) and §16 future (auth).

**Future.**

- Persist all four write targets to a database (Postgres). PLANNED —
  roadmap Phase 1.
- Add an explicit "remember this" button so the auditor can pin a
  specific anomaly into long-term memory. PLANNED — depends on §8.1
  long-term memory.

### 8.3 Read Path — *Partial / mostly Applicable*

**In code today.**

- **Display read.** `Session.history` is rendered in the chat panel.
- **Reuse read.** `Session.analysis` is consumed by `analysis_ask` and
  `reports_reconciliation` to avoid re-running the LLM pipeline.
- **Audit read.** `Session.audit` is concatenated across all sessions
  by `SessionStore.all_audit()` and exposed at `/api/reports/audit`.
- **Prompt-time read.** The `{memory}` placeholder in
  `prompts/anomaly_prompt.txt` is bound to the literal string `"[]"`
  in `detect_anomalies` — i.e. **the read path is stubbed**. The plumb
  is in place; the backing store is not.

**Future.**

- Replace the stub with a real read: top-N most recent confirmed
  anomalies, ranked by recency / severity. PLANNED.
- Add a context-window budget so a long memory does not blow past the
  model's input limit. PLANNED — §11.2 + §22.2.

### 8.4 Forgetting & Expiry — *Partial*

**In code today.**

- All memory is **process-local**: a `uvicorn` restart wipes every
  session and audit entry instantly. This is the closest the app gets
  to a TTL.
- There is no per-user delete endpoint, no cron-style expiry, and no
  GDPR-style purge.

**Future.**

- TTL / sliding-window retention on persisted sessions. PLANNED.
- User-initiated `DELETE /api/agent/session/{id}`. PLANNED.
- Compliance-driven purge (right-to-be-forgotten). PLANNED — depends
  on §16 (auth) and §24.4 (privacy).

### 8.5 Privacy Boundaries — *Partial*

**In code today.**

- **Per-session isolation.** `Session` objects are keyed by random
  UUID4 and only the holder of the UUID can read or advance them
  (`SessionStore.require(session_id)` is called by every route that
  takes a session id).
- **Cross-session leakage.** The chat / analysis / status code paths
  never read another session's `history` or `analysis`. The only
  cross-session aggregator is `/api/reports/audit`, which is intended
  to be admin-only (no auth today, see future).
- **Single-tenant assumption.** All sessions share the same backend
  database connection and the same MySQL credentials.

**Future.**

- Authenticated `/api/reports/audit` so an analyst cannot scrape
  another analyst's events. PLANNED — §16.5.
- Tenant column in any future `sessions` table. PLANNED.
- Encrypted-at-rest fields (Fernet key already pinned in
  `requirements.txt`) for sensitive analyst notes. PLANNED.

---

## 9. Retrieval-Augmented Generation (RAG)

### 9.1 Corpus & Sources — *NA*

**Why NA.** The Anomaly Agent has **no document corpus and no vector
store**. Every prompt is grounded by inline injection of structured
context (column metadata + sampled rows + previously detected
anomalies), not by retrieval from an indexed document set.

**Future conditions for this subsection becoming Applicable.**

- Auditor playbooks, vendor contracts, or SOX policy notes are loaded
  into the system as searchable corpora that the analyst chat can
  cite. PLANNED.

### 9.2 Ingestion Pipeline — *NA*

**Why NA.** No ingestion pipeline exists because there is no corpus
(§9.1). The closest analogue is the SQL fetch path
(`database.fetch_anomaly_data`), which is direct relational access —
not parsing, chunking, or deduplicating documents.

**Future.** PLANNED — depends on §9.1.

### 9.3 Embedding Strategy — *NA*

**Why NA.** No embedding model is loaded; `requirements.txt` does not
pin one. There is no vector representation of anomalies, sessions,
prompts, or column metadata.

**Future.** PLANNED — depends on §9.1.

### 9.4 Retrieval & Ranking — *NA*

**Why NA.** Without an embedding model or a corpus, there is no
retrieval surface. The "selection" of context for each prompt is
hand-coded (e.g. "first 200 rows" in `understand_dataset`, "first 50
rows" for `status_qa`); this is sampling, not retrieval.

**Future.** PLANNED — depends on §9.1.

### 9.5 Context Assembly — *NA*

**Why NA.** Context is assembled by `str.format` substitution into a
prompt template (§6.2). There is no token-budget aware packing, no
citation formatting, no overflow handling.

**Future conditions for this subsection becoming Applicable.**

- Token-aware context packing once any prompt approaches the model's
  input limit. Today the largest single call is the chunked anomaly
  detector at 200 rows of JSON, which is well under any modern
  context window. PLANNED — §11.2 + §22.2.

### 9.6 Evaluation — *NA*

**Why NA.** Recall@k, faithfulness, answer relevance, and groundedness
metrics all presuppose a retrieval step (§9.4). With no retrieval, the
metrics do not apply.

**Future.** PLANNED — depends on §9.1 + §20.2 (LLM evaluation).

---

## 10. Orchestration & Control Flow

### 10.1 Agent Loop — *Applicable*

**In code today.** The Anomaly Agent does **not** use an autonomous
*perceive → plan → act → observe → reflect* loop. It uses a one-step
finite state machine driven by user input: each chat turn is a single
"perceive (read message) → act (transition + maybe call tool) →
observe (return reply)" round. There is no internal looping inside a
turn, no max-step counter, and no reflection step.

The driver lives in `backend/main.py::agent_chat`:

```python
@app.post("/api/agent/chat", response_model=ChatResponse)
def agent_chat(req: ChatRequest) -> ChatResponse:
    sess = store.require(req.session_id)
    sess.add_turn("user", req.message.strip())
    if _is_exit(user_msg): ...
    elif sess.step in {STEP_GREET, STEP_AWAIT_DATES}:
        reply = _handle_await_dates(sess, user_msg)
    elif sess.step == STEP_CONFIRM:
        reply = _handle_confirm(sess, user_msg)
    elif sess.step == STEP_PROCESSING: ...
    elif sess.step == STEP_ERROR: ...
    sess.add_turn("assistant", reply)
    return ChatResponse(...)
```

Step limits, recursion depth, max-tool-calls — all NA today because
each turn is a single transition.

**Future.**

- A multi-step agent loop becomes meaningful only after function
  calling lands (§7.1 future). At that point: cap at N tool calls per
  turn; emit a `step_count` field on each `ChatResponse`. PLANNED.
- Reflection / self-critique step where the LLM grades its own anomaly
  list before returning. PLANNED — §17.4.

### 10.2 Planning Strategies — *NA*

**Why NA.** ReAct, Plan-and-Execute, and Tree-of-Thoughts all assume
the LLM is choosing what to do next. The Anomaly Agent's "plan" is
fixed: the FSM dictates the next action; the LLM only chooses the
*content* of the response, not the *control flow*.

**Future.** Planning becomes meaningful after §7.1 future lands.
PLANNED.

### 10.3 State Machine — *Applicable*

**In code today.** Explicit, hand-rolled. States are constants in
`backend/session_manager.py`:

```python
STEP_GREET       = "greet"
STEP_AWAIT_DATES = "await_dates"
STEP_CONFIRM     = "confirm"
STEP_PROCESSING  = "processing"
STEP_DONE        = "done"
STEP_ERROR       = "error"
```

Transitions:

| From | Input | To | Side effect |
|------|-------|----|-------------|
| `greet` / `await_dates` | free text | `confirm` | `normalize_date_range` + `validate_date_range` |
| `await_dates` | invalid input | `await_dates` | none |
| `confirm` | `confirm` / `yes` / `y` / `ok` / `go` / `run` | `processing` → `done` / `error` | metadata write + Airflow trigger |
| `confirm` | anything else | `await_dates` | re-parse |
| `error` | `retry` / `rerun` | `done` / `error` | re-trigger pipeline |
| any | `exit` / `quit` / `cancel` | `done` | session ends |

Terminal conditions: `STEP_DONE` (success), `STEP_ERROR` (recoverable
via `retry`).

**Future.**

- Add a `STEP_AWAITING_AIRFLOW` once Airflow REST polling is in (§3.1
  future + roadmap Phase 2). The current `done` step optimistically
  fires on a successful trigger. PLANNED.

### 10.4 Interruption & Human-in-the-Loop — *Applicable*

**In code today.**

- **Confirmation gate.** `STEP_CONFIRM` is the explicit human-approval
  step. Nothing writes to the metadata table or invokes Airflow until
  the user types `confirm`.
- **Clarification request.** When `validate_date_range` returns
  `False`, the agent asks again rather than guessing
  (`_handle_await_dates`).
- **Cancel.** `exit`/`quit`/`cancel` at any time terminates the
  session.
- **Retry.** After `STEP_ERROR`, the user types `retry` to re-run
  `_trigger_pipeline`.

**Future.**

- Hand-off to a human reviewer on high-severity anomalies (escalation
  channel). PLANNED — §1.2.
- Mid-run abort during `/api/analysis/setup` (today the request
  blocks until `format_report` returns). PLANNED.

### 10.5 Determinism Levers — *Applicable*

**In code today.**

| Lever | Setting | Where |
|-------|---------|-------|
| Temperature | `0` | `OPENAI_TEMPERATURE=0` in `backend/config.py`; passed into `ChatOpenAI`. |
| Seeded generation | not used | OpenAI's `seed` parameter is not passed (LangChain `ChatOpenAI` does support it; would need a constructor change). |
| Schema-constrained outputs | enforced by prompt + post-parse | JSON-emitting prompts (date_extract, anomaly) declare the JSON shape; `_strip_json_fences` + `json.loads` parse; bad output is dropped (`detect_anomalies`). |
| Required-headings contract | enforced by prompt | `anomaly_format_prompt` (4 headings); `reconciliation_prompt` (5 headings). No runtime check yet (§2.2 future). |

**Future.**

- Pass OpenAI's `seed` parameter for byte-stable replays in the eval
  harness. PLANNED — §20.2.
- Use OpenAI / Claude *response_format=json_schema* (or LangChain's
  `with_structured_output`) for the JSON-emitting roles, replacing
  prompt-based JSON enforcement. PLANNED.

---

## 11. Conversation Design & State

### 11.1 Turn Structure — *Applicable*

**In code today.**

- A *turn* is a single user message + the assistant reply. There is no
  multi-message turn and no tool-call interleaving (§7 future).
- Each turn is one HTTP round-trip: `POST /api/agent/chat` →
  `ChatResponse`.
- The user is gated from typing while the request is in flight
  (`busy` state in `frontend/src/panels/AgentChatPanel.jsx`).

**Future.**

- Multi-message assistant turns once streaming lands (§14.2). PLANNED.
- Inline tool-call traces (e.g. "running SQL ...") once §7.1 future
  is done. PLANNED.

### 11.2 Context Window Management — *Applicable*

**In code today.**

- **Sampling, not summarisation.** `understand_dataset` uses the first
  200 rows. `status_qa` uses the first 50 rows. The chunked anomaly
  detector processes 200 rows per call, returning consolidated
  results.
- **No accumulation across turns.** Every prompt re-builds its full
  context from scratch — `Session.history` is *displayed*, not
  *replayed*. A long chat does not bloat the next prompt.
- **No summarisation, no sliding window, no pinning.** The fixed
  sampling caps are the only form of window management.

**Future.**

- Token-aware truncation of the `{anomalies}` and `{rows}` payloads
  with a deterministic ranking (severity desc, recency desc) before
  truncation. PLANNED.
- Periodic summarisation of `Session.history` once any prompt starts
  replaying it. PLANNED.

### 11.3 Conversation Persistence — *Partial*

**In code today.**

- `Session.history` lives in process memory (§8.1).
- The frontend never stores chat history in `localStorage` or a
  cookie; reloading the page does not restore the chat (the
  `AgentChatPanel` calls `POST /api/agent/start` on every mount).
- There is no replay endpoint, no export endpoint, no history UI
  beyond the active panel.

**Future.**

- Persist `Session.history` to Postgres. PLANNED — roadmap Phase 1.
- `GET /api/agent/sessions` and `GET /api/agent/session/{id}/history`
  for replay / export. PLANNED.
- Chat history sidebar in the UI. PLANNED.

### 11.4 Multi-Session Continuity — *NA*

**Why NA.** Today there is **no bridge** between sessions. Each new
`POST /api/agent/start` allocates a fresh `Session` with empty
`history`, empty `analysis`, and empty `audit`. Prior runs' anomaly
detections are not surfaced — the `{memory}` placeholder is the
literal string `"[]"` (§8.3).

**Future conditions for this subsection becoming Applicable.**

- §8.1 long-term memory lands. At that point the analyst panel can
  surface "you flagged 4 ACME duplicates last week — still suspicious
  this run?". PLANNED.

### 11.5 Conversation Reset & Branching — *Partial*

**In code today.**

- **Reset.** Header *New Session* button in `App.jsx`:
  `handleNewSession()` bumps `resetKey`, which is passed as the `key`
  prop on each panel; React unmounts and re-creates them with empty
  state. The backend `Session` is *abandoned*, not deleted (it
  remains in `SessionStore` until process exit).
- **Branching.** Not supported. There is no fork-this-conversation,
  no share-as-link, no diff between two conversation branches.

**Future.**

- `POST /api/agent/session/{id}/reset` that explicitly drops the old
  session. PLANNED.
- Fork-and-edit: clone a session at turn N, change a date, see the
  difference in the resulting analysis. PLANNED.
- Share-as-link with a read-only token. PLANNED — depends on §16.

---

# Part IV — Frontend & Backend

## 12. Frontend Architecture

### 12.1 Framework & Rendering Strategy — *Applicable*

**In code today.**

| Decision | Value | Where |
|----------|-------|-------|
| Framework | React 18.3 | `frontend/package.json` |
| Bundler / dev server | Vite 5.4 | `frontend/vite.config.js` |
| Rendering | CSR (client-side only); no SSR | `frontend/src/main.jsx` mounts into `#root` |
| Routing | none (single-page, three panels) | `frontend/src/App.jsx` |
| State management | local `useState` + props | no Redux / Zustand / Context store |
| Language | plain JavaScript (no TypeScript) | `.jsx` extension throughout |
| Styling | plain CSS via `:root` variables | `frontend/src/index.css` |
| Dev port / proxy | `:3000` strictPort, `/api` → `:8000` | `frontend/vite.config.js` |

Shared frontend state lives in `App.jsx`: `sessionId`, `activeDelivery`,
`activeContracts`, `processingComplete`, `health`, `resetKey`. Every
other piece of state is local to a panel.

**Future.**

- Adopt TypeScript. Codegen the request / response types from
  `/openapi.json` into `frontend/src/types/`. PLANNED — §15.2.
- Add a route per delivery (e.g. `/run/<run_id>`) once persistence
  lands. PLANNED — §11.3 future.

### 12.2 Component Library — *Partial*

**In code today.** No third-party UI library (no MUI, Chakra, Ant
Design, shadcn). Every primitive is hand-rolled in CSS:

| Primitive | Where |
|-----------|-------|
| Button (`.btn`, `.btn-primary`, `.btn-ghost`, `.btn-sm`) | `frontend/src/index.css` |
| Status chip (`.step-chip`, `.badge`) | same |
| Status card (`.status-card`, with tone variants) | same |
| Grid table (`.grid-table`, sticky header) | same |
| Markdown table (`.md-table-wrap`, `.md-table`) | same |
| Pill (`.pill`) | same |
| Empty / error / muted states | same |

The "library" is therefore the CSS file plus the inline JSX. There is
no Storybook, no design-tokens package shared across repos.

**Future.**

- Extract the primitives into a `frontend/src/components/ui/` folder
  with one component per primitive. PLANNED.
- Share design tokens with the AdminFee Agent via a small NPM
  package. PLANNED — §2.4.

### 12.3 Chat UI Patterns — *Applicable*

**In code today.**

- **Message rendering.** Each turn is a `.chat-msg` block with role
  badge (`You` / `Agent`); assistant turns render through
  `MarkdownRenderer.jsx`, user turns render verbatim with
  `white-space: pre-wrap`.
- **Markdown.** Custom renderer handles headings, bold/italic, inline
  code, fenced code blocks (with `lang-<name>` class), ordered /
  unordered lists, GitHub-style tables, links — see §2.2.
- **Code blocks.** `.code-block` style with monospace font and slight
  background tint.
- **Tool traces.** Today only the SQL view in the analyst panel. The
  generated SQL hides behind a `<details>` element (`Generated SQL`
  summary); rows render in a `.qa-rows` grid table when the safe-SQL
  guard accepts them.
- **Citations.** Inline `code` spans for `invoice_id`, field names,
  table names — driven entirely by the prompts (§2.2).
- **Typing indicator.** Three dots animation in `AgentChatPanel.jsx`
  while a request is in flight.
- **Quick replies.** `Confirm & run` and `Cancel` buttons surface only
  on `step=confirm` (`AgentChatPanel.jsx::quickReply`).

**Future.**

- Streaming render (token by token) once §14.2 lands. PLANNED.
- Inline tool-trace blocks once §7.1 future lands. PLANNED.
- Inline citation popovers (e.g. hover an `invoice_id` to see the
  underlying row). PLANNED.

### 12.4 Input Modalities — *Partial*

**In code today.**

- **Text only.** Each panel uses a `<textarea>` or `<input
  type="text">` (chat panel uses textarea with Enter-to-send).
- **No voice.** No `MediaRecorder`, no Web Speech API.
- **No file upload.** No drag-and-drop, no `<input type="file">`.
- **No image paste.** No clipboard handlers.

**Future.**

- File upload of an off-line CSV or Excel of suspect invoices for
  ad-hoc analysis. PLANNED — §15.3.
- Voice input in the analyst panel for hands-free Q&A. PLANNED.

### 12.5 Accessibility — *Partial*

**In code today.**

- Semantic HTML: `<header>`, `<main>`, `<section>`, `<footer>`,
  proper heading hierarchy.
- Buttons are real `<button>` elements (not div-buttons), so keyboard
  focus and Space/Enter activation work for free.
- Forms use real `<select>`, `<textarea>`, `<input>` elements; Enter
  submits the chat textarea (with `Shift+Enter` for newline).
- Colour-only signals are paired with text labels (the status chip
  shows the state name, not just the colour).

What is **not** done today:

- No WCAG audit, no automated `axe-core` run.
- No explicit `aria-label` on the icon-only brand-dot or step chips.
- No focus ring polish in CSS (relies on browser default).
- No reduced-motion media query.
- No keyboard shortcut for "New Session" or "Refresh".

**Future.**

- WCAG 2.1 AA target: add `aria-label`s, focus rings, reduced-motion
  fallback for the typing indicator. PLANNED.
- Keyboard shortcut layer (`?` opens a help overlay). PLANNED.

---

## 13. Backend Services

### 13.1 Service Boundaries — *Applicable*

**In code today.** Single FastAPI service. There is no gateway, no
orchestrator microservice, no agent-runtime/tool-registry split. The
modules inside the service are organised by responsibility (see §3.2)
but they all run in the same Python process and share the same
`SessionStore` instance.

| Logical responsibility | Module |
|------------------------|--------|
| HTTP edge (gateway-equivalent) | `backend/main.py` (CORS + route handlers) |
| Orchestrator (FSM dispatcher) | `_handle_*` helpers in `backend/main.py` |
| Agent runtime (LLM calls + fallbacks) | `backend/llm_service.py` |
| Tool registry (DB + Airflow) | `backend/database.py`, `backend/airflow_trigger.py` |
| Session storage | `backend/session_manager.py` |
| Configuration | `backend/config.py` |

**Future.**

- Split out the agent runtime if §7.1 future lands and the function-
  calling loop becomes long-running enough to warrant its own process
  (with shared queue / state). PLANNED.
- Extract the SSH trigger into a sidecar so the FastAPI process never
  blocks on Paramiko. PLANNED — §13.5.

### 13.2 Inter-Service Communication — *Partial*

**In code today.** Inside the single FastAPI process: plain function
calls. Across process boundaries:

| External call | Transport |
|---------------|-----------|
| FastAPI ↔ MySQL | TCP/3306 via PyMySQL (sync, blocking). |
| FastAPI ↔ Airflow EC2 host | SSH/22 via Paramiko (sync, blocking). |
| FastAPI ↔ OpenAI | HTTPS via LangChain-OpenAI → `openai` SDK (sync, blocking). |
| Browser ↔ FastAPI | HTTP/JSON via `fetch` (CORS-allow-list-gated). |

There is no asynchronous queue, no pub/sub, no gRPC. All blocking; on
the FastAPI side, each blocking call holds an event-loop thread until
it returns.

**Future.**

- Move SSH triggering to a background task with a queue (Celery /
  RQ). PLANNED — §13.5.
- Add retry / jitter wrapper around the OpenAI call. PLANNED — §26.5.

### 13.3 Data Contracts — *Applicable*

**In code today.** Pydantic 2 models in `backend/main.py` define the
shape of every request and response. The same Pydantic models drive
the auto-generated `/openapi.json` and the Swagger UI at `/docs`.

Examples:

```python
class ChatRequest(BaseModel):
    session_id: str
    message: str

class StatusSummary(BaseModel):
    total_records: int
    anomalies_detected: int
    processing_state: str
    start_date: str | None = None
    end_date: str | None = None
    last_updated: str
```

The frontend `services/api.js` does not import these schemas — it
manually constructs the request bodies and trusts the response shape.

**Future.**

- Codegen TypeScript types from `/openapi.json` into the frontend.
  PLANNED — §15.2.
- Versioned contracts via the `Accept` header (e.g.
  `application/vnd.anomaly.v1+json`). PLANNED — §23.2.
- Contract tests (Schemathesis) in CI. PLANNED — §20.

### 13.4 Service Scaling — *NA*

**Why NA.** The service is intentionally single-process / single-worker
on this branch (uvicorn `--reload` implies one worker). No horizontal
scaling, no hot-path isolation, no statelessness work has been done
because the in-memory `SessionStore` cannot span workers (§4.5).

**Future conditions for this subsection becoming Applicable.**

- A persistent session store lands (§8 future + roadmap Phase 1). At
  that point uvicorn / gunicorn workers can be scaled horizontally.
- Hot-path isolation: dedicate one worker pool to the chat / status
  routes (low latency) and another to `/api/analysis/setup` (long
  blocking calls). PLANNED.

### 13.5 Background Jobs — *NA*

**Why NA.** There is no scheduler, no Celery / RQ / APScheduler, no
DLQ, no idempotency token. The Airflow trigger is the closest thing
to a background job, and even that is invoked synchronously inside an
HTTP request (the response waits for SSH to return).

**Future conditions for this subsection becoming Applicable.**

- Move `_trigger_pipeline` to a background task with a queue so the
  user gets an immediate "queued" reply and the status panel watches
  for completion. PLANNED — §3.1 future + roadmap Phase 2.
- Schedule a nightly `analysis_setup` for the previous day so the
  morning auditor finds a pre-computed report. PLANNED.

---

## 14. Streaming & Real-Time Communication

> **Section orientation.** The Anomaly Agent uses **HTTP polling**, not
> streaming, on this branch. §14 is therefore largely **NA** today;
> §14.5 has a partial analogue.

### 14.1 Transport Choice — *NA (today) / Applicable (planned)*

**In code today.** No SSE, no WebSocket, no HTTP/2 server push.

- Status updates: `StatusMonitorPanel` polls `/api/status/summary` and
  `/api/status/contracts` every 30 seconds (`POLL_MS = 30_000`).
- Chat: request / response per turn (`POST /api/agent/chat`).
- Analysis: blocking request (`POST /api/analysis/setup`) — the user
  waits for understanding + chunked detection + format to finish.

**Future.** Adopt **Server-Sent Events** for the status push and for
streaming LLM tokens. SSE is preferred over WebSockets for this
workload because:

- Reads are one-way (server → client); no duplex needed.
- SSE works through corporate proxies that block WS upgrades.
- It maps cleanly onto the existing `/api/*` HTTP surface.

PLANNED — see roadmap Phase 3.

### 14.2 Token Streaming Protocol — *NA*

**Why NA.** `invoke_llm` calls `.invoke(prompt)` which is the blocking
LangChain method. There is no `.stream()` call on this branch and no
SSE channel to deliver tokens over.

**Future conditions for becoming Applicable.**

- Add a `stream_llm(prompt)` async generator beside `invoke_llm`.
  Wire it to a new `GET /api/agent/chat/stream` SSE endpoint that
  emits `data:` events with partial content. PLANNED.
- Frontend incremental render: append the partial text into the
  current `chat-msg` and flush each animation frame. PLANNED — §14.5.

### 14.3 Tool Call Streaming — *NA*

**Why NA.** No function calling today (§7.1). The closest analogue is
the SQL-then-rows reveal in the analyst panel: `analysis_ask` returns
the answer, the SQL, and the rows in a single response, and the
`<details>` element renders them on click — not progressively as they
become available.

**Future.** Once §7.1 future + §14.2 land, emit a `tool_call_start /
tool_result` event pair per tool invocation. PLANNED.

### 14.4 Reconnection & Resume — *NA*

**Why NA.** No long-lived connection exists today, so there is nothing
to reconnect or resume. Each panel's polling tick is independent — a
dropped network call simply waits 30 s and tries again.

**Future.**

- SSE auto-reconnect via `EventSource` (browser-native). PLANNED.
- Server-side `Last-Event-ID` checkpoints so a reconnecting client
  resumes from the last token / status update. PLANNED.

### 14.5 Client Buffering & Render Cadence — *Partial*

**In code today.** Because there is no streaming, the cadence is
binary: a panel either has data or it shows a "loading" state.

- The chat panel renders a 3-dot `.typing` animation while `busy=true`
  in `AgentChatPanel.jsx`.
- The analysis panel shows `Generating…` while `reconBusy=true` in
  `AnalysisPanel.jsx`.
- The status panel does not show a spinner during refresh; it just
  re-renders when the next tick lands.
- The markdown renderer is fast enough on the full response that
  there is no perceptible delay between `setMessages` and paint.

**Future.**

- For SSE token streaming, smooth the render cadence to one append
  per animation frame (`requestAnimationFrame`) so the text does not
  jitter. PLANNED.
- Skeleton loaders for the analysis sections. PLANNED.

---

## 15. Full-Stack Integration Patterns

### 15.1 API Layer — *Applicable*

**In code today.** REST under `/api/*`, JSON in / JSON out, served by
FastAPI. There is **no** BFF, no GraphQL, no tRPC. The frontend
`services/api.js` is a thin `fetch` wrapper that calls these routes
directly through the Vite proxy (§3.1).

| Group | Routes | Purpose |
|-------|--------|---------|
| Agent | `/api/agent/start`, `/api/agent/chat` | FSM driver |
| Status | `/api/status/summary`, `/api/status/contracts`, `/api/status/ask` | Centre panel |
| Analysis | `/api/analysis/deliveries`, `/api/analysis/setup`, `/api/analysis/ask` | Right panel |
| Reports | `/api/reports/reconciliation`, `/api/reports/audit` | Reconciliation + audit |
| Health | `/api/health` | Liveness + DB check |

Full request / response detail: `doc/api-reference.md`.

**Future.**

- An optional GraphQL layer if the analyst panel needs to compose
  several routes' data into one render. Not justified today. PLANNED
  if the UI grows.

### 15.2 Type Safety Across Stack — *Partial*

**In code today.**

- **Backend.** Pydantic 2 models on every request / response — strong
  typing inside Python.
- **Frontend.** Plain JavaScript; no TypeScript, no JSDoc. The
  frontend reads the response shape by convention.
- **No codegen.** `/openapi.json` is published but not consumed.
- **No contract test.** Nothing fails the build if the backend
  changes a field name.

**Future.**

- Adopt TypeScript on the frontend. PLANNED.
- Codegen TypeScript types from `/openapi.json` into
  `frontend/src/types/`. PLANNED.
- Schemathesis contract test in CI. PLANNED — §20.

### 15.3 File Upload & Asset Pipeline — *NA*

**Why NA.** There is no file upload UI, no presigned-URL flow, no
virus scan, no asset pipeline. The frontend never sends multipart
form data; the backend pins `python-multipart` only because FastAPI
imports it transitively.

**Future.** PLANNED — §12.4 future (CSV / Excel uploads).

### 15.4 Feature Flags & Remote Config — *NA*

**Why NA.** No feature flag provider (LaunchDarkly, GrowthBook,
custom). All toggles today are env vars (`OPENAI_MODEL`,
`OPENAI_TEMPERATURE`, `API_PORT`, etc.) read once at startup.

**Future.**

- A small flag layer for prompt A/B testing (§6.4 future) and for
  rolling out streaming (§14). PLANNED.

### 15.5 Third-Party Integrations — *Applicable*

**In code today.**

| Integration | How it is wired |
|-------------|-----------------|
| OpenAI | `langchain-openai.ChatOpenAI` constructed in `get_llm`. Auth via `OPENAI_API_KEY` (`backend/config.py`). |
| Airflow on EC2 | SSH command via Paramiko (`backend/airflow_trigger.py`). Auth via key file at `SSH_KEY_PATH`. |
| AWS RDS / MySQL | SQLAlchemy + PyMySQL connection string in `DB_URI` (`backend/config.py`). |
| AWS S3 | not used today; `boto3` is pinned for future ingestion. |

There are no OAuth providers, no SaaS connectors, no inbound
webhooks.

**Future.**

- Outbound webhook to a chat tool (Slack / Teams) on completion.
  PLANNED — §1.2.
- Inbound webhook from Airflow on DAG success / failure (replaces
  the polling loop). PLANNED — §3.1 future + roadmap Phase 2.

---

## 16. Authentication, Authorization & Sessions

> **Section orientation.** The Anomaly Agent has **no authentication
> and no authorization** on this branch. §16 is largely **NA** today.
> §16.3 (session management) and §16.5 (audit logging) have partial
> in-code analogues.

### 16.1 Identity Providers — *NA*

**Why NA.** No SSO, no OAuth, no magic-link, no SAML, no OIDC. The
frontend never asks the user who they are; the backend never reads
an `Authorization` header. The header is the operator's role,
implicitly.

**Future.** OIDC against the corporate IdP (Azure AD or Google).
PLANNED — roadmap Phase 5.

### 16.2 Authorization Model — *NA*

**Why NA.** No RBAC, no ABAC, no per-resource permissions. Every
session can call every endpoint; the only access control is **CORS**
(`localhost:3000` only) and **read-only SQL** (`run_select_safely`).

**Future.**

- Two roles to start: `analyst` (read + analysis Q&A) and `admin`
  (trigger pipeline + view audit). PLANNED — roadmap Phase 5.
- Per-tenant isolation column on every persisted record. PLANNED.

### 16.3 Session Management — *Applicable*

**In code today.**

- **Session id.** UUID4 string, generated by `SessionStore.create()`.
  Returned by `/api/agent/start`; the frontend stores it in component
  state and includes it in every subsequent request body. **It is not
  a cookie, not an HTTP-only token, and not bound to a device.**
- **Lifetime.** Bounded by the FastAPI process. There is no idle TTL
  and no explicit revocation.
- **Concurrency.** `SessionStore` is guarded by a `threading.Lock`.
- **Reset.** *New Session* button creates a fresh `Session`; the old
  one is abandoned but not deleted (§11.5).

**Future.**

- HTTP-only cookies for the session token. PLANNED.
- Idle TTL + sliding window on persisted sessions. PLANNED — §8.4.
- Explicit revocation endpoint. PLANNED — §11.5.

### 16.4 API Keys & Service Accounts — *NA*

**Why NA.** No programmatic access surface today. Every route is
designed for a human-in-the-loop session — there is no service
account, no API key, no token rotation policy.

**Future.**

- API key for the `/api/reports/*` routes if a downstream BI tool
  needs to ingest the audit log. PLANNED.

### 16.5 Audit Logging — *Applicable*

**In code today.**

- Every chat turn, FSM transition, metadata write, Airflow trigger,
  analysis setup, and reconciliation logs an audit event via
  `Session.log(event, detail)` — see `backend/main.py`.
- `SessionStore.all_audit()` aggregates events across all sessions in
  the process and exposes them at `GET /api/reports/audit`,
  newest-first.

| Event | Detail payload |
|-------|----------------|
| `session_start` | (none) |
| `dates_parsed` | `{start_date, end_date}` |
| `metadata_written` | `{start, end}` |
| `airflow_trigger` | `{ok, run_id, stderr}` |
| `analysis_setup` | `{delivery_id}` |
| `analysis_ready` | `{anomaly_count}` |
| `analysis_ask` | `{question, sql}` |
| `reconciliation` | `{anomaly_count}` |

The log is **in-memory only** today (§8.4) and **un-authenticated**
(any caller of `/api/reports/audit` sees every session's events).

**Future.**

- Persist audit events to a dedicated `audit_events` table. PLANNED —
  roadmap Phase 1.
- Lock `/api/reports/audit` behind an `admin` role. PLANNED — §16.2.
- Tamper-evident audit (hash chain or immutable storage). PLANNED.

---

# Part V — Safety & Security

## 17. Guardrails & Alignment

### 17.1 Policy Layer — *NA*

**Why NA.** There is no policy classifier, no allowed/disallowed topic
list, and no escalation policy on this branch. The Anomaly Agent's
"policy" is implicit in the prompts: each role tells the model what to
output and what to refuse, but there is no separate guardrail layer
that inspects either the prompt or the response.

This is acceptable today because:

- The agent is single-tenant, internal, behind localhost CORS.
- The prompts only ever execute against a known, structured table
  (`anomaly.duplicate_ap_invoice`).
- The only side effects are `upsert_anomaly_metadata` (idempotent) and
  the SSH trigger (gated by `STEP_CONFIRM`).

**Future.**

- A pre-LLM policy layer that checks the user's free-text input for
  obviously off-task content (e.g. "ignore previous instructions").
  PLANNED.
- A post-LLM policy layer that validates the output against the
  required-headings contract before render. PLANNED — §2.2 future.
- An explicit escalation rule for high-severity anomaly volumes.
  PLANNED — §1.2.

### 17.2 Input Filtering — *Partial*

**In code today.**

| Filter | Where |
|--------|-------|
| Date format / range validation | `backend/llm_service.py::validate_date_range` — invalid input bounces back to the user, never reaches `_trigger_pipeline`. |
| FSM gate | The agent only calls `normalize_date_range` in `STEP_AWAIT_DATES`; user input in other steps is constrained (`confirm`, `retry`, `cancel`). |
| Length limit | None today; FastAPI / Pydantic will reject oversized JSON, but there is no per-field cap. |
| Prompt-injection detection | None. The free-text `{question}` and `{input}` placeholders are inserted verbatim. |
| PII redaction | None. The auditor's text is captured as-is into `Session.history` and `Session.audit`. |

**Future.**

- Prompt-injection classifier (small model, sub-100ms) on the chat
  panel input and the analyst Q&A input. PLANNED.
- PII redaction before any text is sent to the LLM (the AP dataset
  itself may contain vendor names but not personal PII; auditor notes
  could). PLANNED.
- Length cap (e.g. 4 KB per message) enforced by Pydantic
  `Field(max_length=...)`. PLANNED.

### 17.3 Output Filtering — *Partial*

**In code today.**

| Filter | Where |
|--------|-------|
| HTML escape on every rendered string | `frontend/src/components/MarkdownRenderer.jsx::escapeHtml` runs before any tag injection. Closes the XSS path. |
| JSON shape parse | `_strip_json_fences` + `json.loads` in `llm_service.py` reject malformed responses; the chunk is dropped on parse failure. |
| Read-only SQL guard | `database.run_select_safely` rejects any non-SELECT statement and any of `insert/update/delete/drop/alter/truncate`. |
| Toxicity / hallucination classifier | None today. |
| Citation verification | None today. The `invoice_id` cited in an anomaly is *believed*, not cross-checked against the rows passed to the prompt. |

**Future.**

- Citation verification: every `invoice_id` in the LLM's anomaly list
  must match a record in the chunk that produced it; un-matched IDs
  are dropped. PLANNED — §17.4.
- A "did the LLM emit all required headings?" check before render.
  PLANNED — §2.2 future.
- Optional toxicity pass on the analyst chatbot output. PLANNED.

### 17.4 Alignment Evaluations — *NA*

**Why NA.** No red-team suite, no regression tests for safety
properties (e.g. "the SQL guard never lets an UPDATE through"), no
periodic alignment eval. The wrapper code refuses bad SQL at runtime,
but no automated test exercises the refusal.

**Future.**

- A `tests/safety/` fixture with adversarial inputs (prompt
  injections, destructive SQL, overly long messages) replayed in CI.
  PLANNED — §20.2.
- Citation-verification eval (§17.3 future) wired into nightly run.
  PLANNED.

### 17.5 Graceful Refusal — *Partial*

**In code today.**

- **Date input refusal.** *"I couldn't read that date range"* is the
  canonical refusal for §10.4 / §17.2. It includes an example so the
  user can self-correct.
- **Out-of-context Q&A refusal.** Driven entirely by the prompt
  (`anomaly_chat_prompt.txt` says *"If the answer is not supported by
  the context, say so plainly..."*). The wrapper has no
  pre/post-check; we trust the model to comply.
- **No appeal path.** The auditor cannot escalate or override a
  refusal — the only remedy is to rephrase.

**Future.**

- Canonical refusal templates per refusal class (out-of-scope,
  policy, missing data). PLANNED.
- An appeal path (e.g. "explain why" link) that opens a structured
  feedback form. PLANNED — §19.4.

---

## 18. Threat Modeling & Defense-in-Depth

### 18.1 Threat Model — *Partial*

**In code today.** No formal STRIDE document. The de-facto threat
model — the one the code already mitigates — is:

| Threat | Mitigation in code |
|--------|---------------------|
| **Spoofing.** Bad actor calls the API as a different "user". | NA today (no auth) — single-tenant, localhost CORS. PLANNED §16. |
| **Tampering — destructive SQL via Q&A.** LLM emits `DROP TABLE` or `UPDATE`; backend executes it. | `database.run_select_safely` rejects non-SELECT and destructive verbs; refusal happens *before* the query is sent. |
| **Tampering — unintended Airflow trigger.** A user reaches the trigger without confirmation. | The FSM gates trigger on `STEP_CONFIRM`; the chat reply explicitly asks for the keyword `confirm`. |
| **Repudiation.** "I never triggered that DAG." | `Session.log("airflow_trigger", {ok, run_id, stderr})` records every attempt. In-memory only today. PLANNED §16.5 future. |
| **Information disclosure — secrets in logs.** The OpenAI API key shows up in stack traces. | Secrets are loaded once into env / `os.environ`; tracebacks log the *type* of error, not the body. The legacy reference scripts at the repo root, however, contain a hard-coded key — see roadmap Phase 0. |
| **Information disclosure — XSS via LLM output.** Model emits `<script>...`. | `MarkdownRenderer.escapeHtml` strips it before any tag injection. |
| **Information disclosure — cross-session leakage.** Session A reads Session B. | Each route requires the caller's `session_id`; no other session is ever read. The audit endpoint is the only aggregator and is documented as admin-only. |
| **Denial of service.** Caller floods `/api/analysis/setup` to exhaust the LLM quota. | NA today (no rate limit). PLANNED §23.3. |
| **Elevation of privilege.** Auditor performs an admin action. | NA today (no role distinction). PLANNED §16.2. |

**Future.**

- A formal STRIDE document with adversary, asset, and attack-surface
  enumerations once the surface widens (auth, multi-tenant). PLANNED.

### 18.2 Prompt Injection Defenses — *Partial*

**In code today.**

- **Trusted vs untrusted content boundary.** User free text *only*
  enters prompts via dedicated placeholders (`{input}`, `{question}`).
  The prompt instructions are part of the file checked into git; user
  text is never concatenated into the instruction block.
- **No tool-execution side effects from the LLM directly.** The LLM
  produces JSON or markdown; the backend interprets it. The most
  dangerous tool — SQL execution — is gated by `run_select_safely`.
- **JSON-only enforcement** for date-extract and anomaly-detect roles
  reduces the attack surface (a malicious instruction would have to
  produce parseable JSON).

What is **not** done today:

- No detection of prompt-injection patterns ("ignore previous
  instructions", "you are now ...").
- No URL / link allow-list for content the LLM might surface.
- No sandboxing of tool calls (because there are no LLM-driven tool
  calls; see §7.1).

**Future.**

- A small classifier on incoming free text. PLANNED.
- Once function calling lands (§7.1 future), instruction hierarchy:
  *system* > *prompt* > *tool result* > *user*. PLANNED.

### 18.3 Data Exfiltration Prevention — *Partial*

**In code today.**

- The LLM never emits raw URLs as tool calls because there are no
  tool calls. It can mention URLs in markdown; the renderer renders
  them as `<a target="_blank" rel="noreferrer noopener">...`.
- There is no egress allow-list; the FastAPI process can talk to any
  outbound IP the host can reach.
- The LLM has access only to what is passed in the prompt — column
  metadata + sampled rows + previously detected anomalies.

What is **not** done today:

- No network egress filtering.
- No automatic redaction of `{rows}` / `{anomalies}` payloads.
- No detection of data-exfiltration prompt patterns ("dump all rows
  as a base64 string").

**Future.**

- Egress allow-list at the host firewall (OpenAI, RDS, Airflow EC2
  only). PLANNED — §25.4.
- Output redaction pass for known sensitive fields. PLANNED.

### 18.4 Secrets & Key Management — *Partial*

**In code today.**

- `.env` loader (`python-dotenv`) reads `OPENAI_API_KEY`, `DB_URI`,
  `SSH_KEY_PATH`, etc. (`backend/config.py`).
- `.env` is gitignored.
- `cryptography` (Fernet) is pinned in `requirements.txt` but **not
  yet used**.
- The legacy reference scripts at the repo root contain a hard-coded
  OpenAI key — flagged in `doc/roadmap.md` Phase 0 ("credential
  cleanup") as the highest-priority security task.

**Future.**

- Strip the hard-coded key from the legacy scripts; rotate the leaked
  key. PLANNED — roadmap Phase 0 (highest priority).
- Move secrets to AWS Secrets Manager / HashiCorp Vault for prod.
  PLANNED — roadmap Phase 6.
- Use Fernet to encrypt analyst notes at rest once §8 future lands.
  PLANNED.
- Add a `detect-secrets` pre-commit hook so a committed key fails the
  hook. PLANNED.

### 18.5 Supply Chain Security — *NA*

**Why NA.** No dependency scanning, no SBOM generation, no model
provenance check, no container signing on this branch. The pinned
versions in `requirements.txt` and `package.json` are the only
control.

**Future.**

- Run `pip-audit` and `npm audit` in CI. PLANNED — §20.5.
- Generate an SBOM (CycloneDX). PLANNED.
- Verify the OpenAI model version response on startup so a silent
  vendor swap is detected. PLANNED — §5.5.

### 18.6 Incident Response — *NA*

**Why NA.** No runbook, no severity matrix, no on-call rotation, no
postmortem template. The audit log (§16.5) is the closest thing to a
post-incident artefact.

**Future.**

- Severity matrix (SEV-1 = pipeline trigger fires unauthorised; SEV-2
  = LLM emits hallucinated `invoice_id`s; SEV-3 = UI regression).
  PLANNED.
- Postmortem template under `doc/incidents/`. PLANNED.

---

*Last updated for branch `claude/anomaly-agent-frontend-s9ygV`. Sections
19 and beyond will be added in subsequent commits.*

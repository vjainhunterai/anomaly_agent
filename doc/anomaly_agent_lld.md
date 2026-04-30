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

*Last updated for branch `claude/anomaly-agent-frontend-s9ygV`. Sections
6 and beyond will be added in subsequent commits.*

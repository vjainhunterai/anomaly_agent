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

*Last updated for branch `claude/anomaly-agent-frontend-s9ygV`. Sections
3 and beyond will be added in subsequent commits.*

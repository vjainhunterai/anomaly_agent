# Roadmap

This page is the forward-looking companion to
[`feature-status.md`](./feature-status.md). Everything here is **PLANNED**
unless it has been promoted to IMPLEMENTED in `feature-status.md` and a
matching code path exists.

The phases are sized so each one is shippable on its own; you do not need
to do them in order, but the dependencies in the right column tell you
what blocks what.

## Phase 0 -- Hardening (already mostly done)

| Item | Why | Depends on |
|------|-----|------------|
| Pinned dependencies in `backend/requirements.txt` and `frontend/package.json` | Reproducible installs | -- |
| `.env`-driven config with `.env.example` checked in | No secrets in git | -- |
| CORS locked to localhost | Block stray cross-origin calls | -- |
| Read-only SQL guard | Cannot accidentally mutate via Q&A | -- |
| Markdown renderer escapes HTML | Avoid XSS in rendered LLM output | -- |

The remaining Phase 0 task is the credential cleanup below.

### TODO -- credential cleanup
- Strip the hard-coded `OPENAI_API_KEY` from
  `anomaly_processing_agent.py` and `anomaly_analyst.py` (legacy scripts);
  point them at `os.environ` instead, mirroring `backend/config.py`.
- Rotate the leaked key in OpenAI's dashboard.
- Add a pre-commit hook (e.g. `detect-secrets`) so it cannot recur.

## Phase 1 -- Persistence

Goal: surviving a backend restart should not lose user state.

| Item | Notes |
|------|-------|
| Persistent session store | Postgres or Redis behind the existing `SessionStore` interface in `backend/session_manager.py`. Keep the in-memory implementation for tests. |
| Persistent audit log | Move `Session.audit` to its own `audit_events` table; add filtering by session/event/time on `/api/reports/audit`. |
| Memory-backed anomaly detection | Wire a `memory` table (or `memory.json`) into `prompts/anomaly_prompt.txt` so prior runs influence the next. |
| Migrations | Add Alembic so schema changes are tracked. |

## Phase 2 -- Real Airflow feedback

Goal: the chat panel should report SUCCESS / FAILED, not just "triggered".

| Item | Notes |
|------|-------|
| Airflow REST polling | After `airflow_trigger.trigger_airflow_dag` succeeds, schedule a background task that polls `GET /api/v1/dags/<dag_id>/dagRuns/<run_id>`. |
| Status pushes | Push state changes onto the session so the polling status panel sees them within one tick. |
| DAG task breakdown | Expose per-task progress in the status cards. |
| Configurable retry | Replace the single SSH attempt with retries + jitter; surface the attempt count in `airflow_status`. |

## Phase 3 -- Push instead of poll

Goal: live updates without 30-second lag.

| Item | Notes |
|------|-------|
| Server-Sent Events on `/api/status/stream` | Same payload as `/summary` but pushed. Falls back to polling if the connection drops. |
| Streaming LLM output | Switch `invoke_llm` to LangChain's streaming API; emit tokens over SSE so the chat panel renders progressively. |
| Backpressure handling | Drop intermediate updates if the client cannot keep up. |

Phase 3 depends on Phase 1 (a persistent store) only if you want the
stream to survive reconnects.

## Phase 4 -- Multi-domain anomaly support

Goal: any anomaly table, not just `anomaly.duplicate_ap_invoice`.

| Item | Notes |
|------|-------|
| Domain registry | A YAML or DB-backed list of `(table, description, prompt_dir)` tuples. |
| Per-domain prompt directories | `prompts/duplicate_ap_invoice/`, `prompts/<other>/`, etc. |
| Domain picker in the chat panel | Adds a `step=pick_domain` before `await_dates`. |
| Per-domain reconciliation rules | Pluggable Python module per domain. |

## Phase 5 -- Auth & multi-tenant

Goal: more than one analyst can use the system safely.

| Item | Notes |
|------|-------|
| OIDC/SSO (Azure AD or Google) | Issued JWT carried as `Authorization: Bearer ...`. |
| Per-user session scoping | `SessionStore` keys become `(user_id, session_id)`. |
| RBAC | At least two roles: `analyst` (read + analysis) and `admin` (trigger pipeline + view audit). |
| Rate limiting | Per-user token bucket on `/api/analysis/*` and `/api/agent/*`. |
| Frontend login page | Hidden when running localhost-only. |

## Phase 6 -- Production deployment

Goal: ship beyond a developer laptop.

| Item | Notes |
|------|-------|
| Dockerfile for backend (uvicorn + gunicorn workers) | Multi-stage; copy `prompts/` into the image. |
| Dockerfile for frontend (nginx serving `dist/`) | Or a single image with nginx fronting uvicorn. |
| `docker-compose.yml` | dev convenience; mirrors prod topology. |
| GitHub Actions CI | Lint, type-check (PLANNED), test, build. |
| Production secrets in AWS Secrets Manager / Vault | Replace `.env` for non-dev. |
| TLS termination via ALB or nginx | Required if the app leaves localhost. |
| Health probes | `/api/health` is already there; wire it into the orchestrator. |
| Structured logs (JSON) | Replace the current Python logging format. |

## Phase 7 -- Analyst UX

Goal: make the analysis panel a tool, not a demo.

| Item | Notes |
|------|-------|
| CSV / Excel / PDF export of the anomaly table | Server-side via Pandas (`pandas` is already pinned). |
| Side-by-side delivery comparison | Render two `final_output` reports in a diff view. |
| Drill-down on a single anomaly | Click a row -> modal with raw record + neighbours. |
| Saved questions / pinboards | Per-user list of recurring questions. |
| Light theme + i18n | CSS variables already factored; the renderer needs a theme switcher. |

## Phase 8 -- Quality

| Item | Notes |
|------|-------|
| Pytest suite for the backend FSM (mock LLM + DB) | Cover `_handle_*` transitions and the SQL guard. |
| Vitest + React Testing Library for the panels | Cover the ref-gating logic in `StatusMonitorPanel` -- it is the most subtle piece. |
| LLM eval harness | Replay a fixture set of inputs; diff outputs against goldens. |
| End-to-end Playwright test | Type a date, confirm, watch the analysis panel populate. |

## What we are deliberately not doing yet

- LangGraph in the backend. The legacy scripts use it; the web app uses a
  hand-rolled FSM because the UI needs one HTTP call per step and
  LangGraph adds complexity without a payoff at this size.
- A second LLM provider. Anthropic / Bedrock / Ollama support is easy to
  add behind `get_llm`, but until there is a concrete use case the extra
  surface area is not worth it.
- A microservice split. One FastAPI app + one React app is the right
  shape until throughput or team boundaries justify breaking it up.

When any of these change, update this file in the same PR.

# Anomaly Agent — Documentation

This folder is the canonical reference for the Anomaly Agent web application.
Each page is grounded in the source code as it exists on
`claude/anomaly-agent-frontend-s9ygV`. Every claim about "what works today"
maps to a real file/line in the repo; every claim about "what is planned"
is explicitly labelled.

## Reading order

| # | Document | What it covers |
|---|----------|----------------|
| 1 | [`feature-status.md`](./feature-status.md) | **The headline matrix: every feature, marked IMPLEMENTED or PLANNED.** Start here. |
| 2 | [`architecture.md`](./architecture.md) | System layout, panel responsibilities, data flow, design choices. |
| 3 | [`api-reference.md`](./api-reference.md) | Every REST endpoint with request/response examples. |
| 4 | [`setup-windows.md`](./setup-windows.md) | Running on Windows, including admin (UAC) elevation. |
| 5 | [`prompts.md`](./prompts.md) | Catalogue of all `prompts/*.txt` templates and their placeholders. |
| 6 | [`roadmap.md`](./roadmap.md) | Phased plan for moving from current MVP to production. |

## Repository orientation (today)

```
anomaly_agent/
|-- backend/                   FastAPI app (port 8000)
|   |-- main.py                All route handlers
|   |-- database.py            SQLAlchemy + raw SQL helpers
|   |-- llm_service.py         LLM wrapper with regex fallbacks
|   |-- airflow_trigger.py     Paramiko SSH trigger
|   |-- session_manager.py     In-memory session store (UUID keyed)
|   |-- config.py              Env loader
|   `-- requirements.txt       Pinned deps (FastAPI 0.115, SQLAlchemy 2, etc.)
|
|-- frontend/                  React 18 + Vite 5 (port 3000, /api proxy)
|   |-- src/App.jsx            3-panel shell + shared state
|   |-- src/panels/            AgentChat, StatusMonitor, Analysis
|   |-- src/components/        MarkdownRenderer
|   |-- src/services/api.js    Centralised fetch wrapper
|   `-- src/index.css          All styles
|
|-- prompts/                   LLM prompt templates
|-- doc/                       <-- you are here
|-- run_backend.py             uvicorn entrypoint
|-- anomaly_processing_agent.py  Original LangGraph script (reference only)
|-- anomaly_analyst.py           Original LangGraph script (reference only)
|-- .env.example
`-- README.md
```

## Conventions used in these docs

- **IMPLEMENTED** — the feature is wired end-to-end on this branch and runs
  against real services (with the caveat that the LLM and DB must be
  reachable). A file path is cited.
- **PARTIAL** — the wiring is in place but a portion is stubbed, regex-only,
  or missing a backing data source.
- **PLANNED** — not in the code today; documented here so the team knows the
  intended direction.

If a feature is not labelled, it is **not in scope** for the current branch.

## How to keep these docs honest

When you change behaviour:
1. Search this folder for any matching claim and update it in the same PR.
2. If you ship a PLANNED item, move it to IMPLEMENTED in
   `feature-status.md` and cite the new code path.
3. Do not add aspirational text without the PLANNED label.

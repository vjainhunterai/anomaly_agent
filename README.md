# Anomaly Agent

Full-stack web app that drives the duplicate Accounts Payable invoice anomaly
pipeline. The architecture mirrors the AdminFee Agent: a 3-panel React UI on
top of a FastAPI backend that wraps the existing LangGraph/LLM logic.

```
┌──────────────────────┬──────────────────────┬──────────────────────┐
│  AgentChatPanel      │  StatusMonitorPanel  │  AnalysisPanel       │
│  step-based FSM chat │  polls every 30 s    │  auto reconciliation │
│  (date range entry)  │  status + table      │  + follow-up Q&A     │
└──────────────────────┴──────────────────────┴──────────────────────┘
```

## Tech

**Frontend** — React 18 + Vite 5, plain JS, plain CSS, no UI library, `/api`
proxied to `http://localhost:8000`.

**Backend** — FastAPI 0.115 + Pydantic 2.9 + Uvicorn, SQLAlchemy 2 + PyMySQL,
LangChain-OpenAI (GPT-4.1-mini, swappable), Boto3, Paramiko, Pandas,
Cryptography (Fernet).

## Windows dev quick-start

> Requires: **Python 3.11+**, **Node 18+**, and (for SSH DAG trigger) a
> readable `.pem` key. Some actions hit AWS RDS, so VPN/proxy must allow it.

### 1. Clone + env

```powershell
git clone https://github.com/vjainhunterai/anomaly_agent
cd anomaly_agent
copy .env.example .env
# then edit .env with real OPENAI_API_KEY, DB_URI, SSH_KEY_PATH
```

### 2. Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cd ..
python run_backend.py
```

Backend listens on `http://localhost:8000`. `--reload` is on, so file edits
hot-restart.

### 3. Frontend

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open **http://localhost:3000** in Chrome or Edge.

### 4. Run as Administrator (optional)

If the Airflow SSH step or DB access needs admin privileges on your machine,
right-click the PowerShell / Windows Terminal shortcut and choose
**"Run as administrator"** before step 2. The FastAPI process inherits
those privileges; the React dev server does not need them.

## Project layout

```
anomaly_agent/
├── backend/
│   ├── main.py              # FastAPI app + all routes
│   ├── database.py          # SQLAlchemy engine + raw SQL helpers
│   ├── llm_service.py       # LLM wrapper: normalize, SQL, analyze, format
│   ├── airflow_trigger.py   # SSH-based DAG trigger via Paramiko
│   ├── session_manager.py   # In-memory session store (UUID keyed)
│   ├── config.py            # env + constants
│   └── requirements.txt
├── prompts/
│   ├── date_extract_prompt.txt
│   ├── understanding_prompt.txt
│   ├── anomaly_prompt.txt
│   ├── anomaly_format_prompt.txt
│   ├── anomaly_chat_prompt.txt
│   ├── status_prompt.txt
│   ├── sql_prompt.txt
│   └── reconciliation_prompt.txt
├── frontend/
│   ├── index.html
│   ├── vite.config.js
│   ├── package.json
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       ├── index.css
│       ├── panels/
│       │   ├── AgentChatPanel.jsx
│       │   ├── StatusMonitorPanel.jsx
│       │   └── AnalysisPanel.jsx
│       ├── components/
│       │   └── MarkdownRenderer.jsx
│       └── services/
│           └── api.js
├── run_backend.py
├── anomaly_processing_agent.py   # original LangGraph script (reference)
├── anomaly_analyst.py            # original LangGraph script (reference)
├── .env.example
└── README.md
```

## API surface

| Method | Path                           | Purpose                                      |
|-------:|--------------------------------|----------------------------------------------|
| POST   | `/api/agent/start`             | Create new session, return greeting          |
| POST   | `/api/agent/chat`              | Send a message; advances the FSM             |
| GET    | `/api/status/summary`          | Counts + processing state                    |
| GET    | `/api/status/contracts`        | Per-record table (flagged vs processed)      |
| POST   | `/api/status/ask`              | Free-form Q&A about current status           |
| GET    | `/api/analysis/deliveries`     | Available runs (metadata range)              |
| POST   | `/api/analysis/setup`          | Run understanding + anomaly detection        |
| POST   | `/api/analysis/ask`            | Follow-up Q&A with optional SQL              |
| POST   | `/api/reports/reconciliation`  | Structured reconciliation report             |
| GET    | `/api/reports/audit`           | Cross-session audit trail                    |
| GET    | `/api/health`                  | Liveness + DB check                          |

## Behavioral notes

- **Chat FSM** — backend holds the state: `await_dates → confirm → processing
  → done | error`. The UI is stateless over that.
- **Status polling** — 30 s interval; completion fires exactly once per run
  via `processingStartedRef + completionFiredRef` gates.
- **Auto reconciliation** — when the status monitor transitions to
  `complete`, the analysis panel runs setup and immediately requests the
  reconciliation report.
- **LLM fallbacks** — every LLM call has a regex / deterministic fallback so
  the UI degrades instead of crashing (see `llm_service.py`).
- **SQL safety** — `/api/analysis/ask` may generate SQL; `run_select_safely`
  refuses non-`SELECT` statements.
- **New Session** — resets all three panels (`key` prop on each) and starts
  a fresh backend session.

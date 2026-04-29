# Setup -- Windows (Development & Admin Run)

This page is the source of truth for getting the app running on a Windows
laptop. The "admin" path is documented because the SSH key lives in the
user profile and some corporate environments restrict outbound DB / SSH
to elevated processes.

## Prerequisites

| Tool | Tested version | Why |
|------|----------------|-----|
| Python | 3.11+ | FastAPI 0.115, SQLAlchemy 2.0, Pydantic 2.9 require it. |
| Node.js | 18 LTS or 20 LTS | Vite 5 + React 18. |
| Git | any recent | for cloning. |
| Chrome or Edge | latest | the markdown renderer relies on modern CSS. |
| OpenSSH client | bundled with Windows 10/11 | not needed for the app itself but useful for verifying the `.pem` works. |

Network requirements:
- Outbound `:443` to `api.openai.com` (or whatever endpoint
  `ChatOpenAI` uses).
- Outbound `:3306` to the AWS RDS host in `DB_URI`.
- Outbound `:22` to the Ubuntu Airflow host.

## 1. Clone & branch

```powershell
git clone https://github.com/vjainhunterai/anomaly_agent
cd anomaly_agent
git switch claude/anomaly-agent-frontend-s9ygV
```

## 2. Configure secrets

```powershell
copy .env.example .env
notepad .env
```

Fill in:

| Key | Notes |
|-----|-------|
| `OPENAI_API_KEY` | Required. Without it, every LLM call returns the regex / static fallback. |
| `OPENAI_MODEL` | Defaults to `gpt-4.1-mini`. Swap freely. |
| `DB_URI` | Full SQLAlchemy URL, e.g. `mysql+pymysql://user:pass@host:3306/joblog_metadata`. |
| `SSH_KEY_PATH` | Absolute Windows path. Use single backslashes inside double quotes, or doubled-up `\\`. The file's NTFS permissions must allow only your user (Paramiko will fail otherwise on stricter setups). |
| `AIRFLOW_CMD` | Remote command. Defaults to the AdminFee DAG name; change for the anomaly DAG when it exists. |
| `UBUNTU_HOST` | `user@ip`. Defaults to the dev EC2 host in the legacy script. |

The hard-coded credentials in the legacy `anomaly_processing_agent.py`
and `anomaly_analyst.py` are **not** read by the FastAPI backend -- those
files are kept only as reference. PLANNED: scrub the hard-coded key from
the legacy scripts (see `roadmap.md`).

## 3. Backend

### Standard run

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cd ..
python run_backend.py
```

Expected output:

```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

Verify:

```powershell
curl http://localhost:8000/api/health
# -> {"status":"ok","db":"ok","time":"..."}
```

### Admin (Run as Administrator)

You only need this if you hit one of these symptoms:
- `paramiko.ssh_exception.SSHException` about key permissions.
- `OperationalError` from PyMySQL even though VPN is connected.
- A corporate DLP / endpoint agent blocks outbound traffic from
  non-elevated processes.

Steps:

1. Press `Start`, type **Windows Terminal** (or PowerShell).
2. Right-click -> **Run as administrator**. Accept UAC.
3. `cd C:\path\to\anomaly_agent`
4. Activate the venv and run `python run_backend.py` exactly as above.

The FastAPI process inherits administrator privileges; the React dev
server does **not** need them and should run in a normal terminal.

> Note: when you elevate, the `HOME` / `USERPROFILE` may resolve to the
> administrator profile rather than your own. If `SSH_KEY_PATH` is in
> `C:\Users\you\Desktop\...`, keep the absolute path in `.env` so the
> elevated process still finds it.

## 4. Frontend

In a **second** terminal (does not need admin):

```powershell
cd frontend
npm install
npm run dev
```

Expected output:

```
VITE v5.x.x  ready in xxx ms
->  Local:   http://localhost:3000/
```

Open `http://localhost:3000` in Chrome or Edge.

## 5. Smoke test

1. Header badge reads **backend ok** (green).
2. The chat panel greets you and the step chip shows **Awaiting date range**.
3. Type `2024-01-01 to 2024-12-31` -> step flips to **Confirm range**.
4. Click **Confirm & run**. Expected behaviour depends on whether the SSH
   trigger succeeds:
   - Success -> assistant message shows the run id; status panel is now
     polling.
   - Failure -> assistant shows the SSH `stderr`; type `retry` after
     fixing the underlying issue.
5. After the status state moves to `complete`, the analysis panel auto-runs
   setup + reconciliation.

## 6. Stopping the app

| Process | Stop with |
|---------|-----------|
| uvicorn | Ctrl+C in its terminal |
| Vite    | Ctrl+C in its terminal |

In-memory sessions are dropped when the backend stops -- there is no
persistent store yet. PLANNED: Postgres-backed sessions.

## 7. Common Windows issues

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `Could not find a version that satisfies the requirement ...` during `pip install` | Python is older than 3.11. | Install 3.11 or 3.12 from python.org and recreate the venv. |
| `WinError 10013` on port 8000 | Another process owns the port. | `netstat -ano | findstr :8000`, kill the PID, or set `API_PORT=8001` in `.env`. |
| `Access is denied` when activating the venv | PowerShell execution policy. | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. |
| Vite says `Port 3000 is in use` | Vite is configured `strictPort: true`. | Stop the other process or change the port in `frontend/vite.config.js`. The backend CORS list will then need to match. |
| `paramiko.ssh_exception.AuthenticationException` | Wrong key path or wrong key permissions. | Open the file in File Explorer -> Properties -> Security -> remove inherited permissions, leave only your user. |
| `OperationalError: (2003, "Can't connect to MySQL server")` | RDS not reachable; check VPN and `NO_PROXY` env. The app sets `NO_PROXY=172.31.27.7` automatically. | If your DB host is different, add it to your shell's `NO_PROXY` before launching uvicorn. |

## 8. Production-style run

PLANNED. There is no Dockerfile, gunicorn config, or systemd unit on this
branch. See `roadmap.md` for the deployment milestones.

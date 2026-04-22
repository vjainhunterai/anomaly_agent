Run (Windows)

copy .env.example .env and fill in OPENAI_API_KEY / DB_URI / SSH_KEY_PATH
In an elevated PowerShell (right-click → Run as administrator): cd backend; python -m venv .venv; .venv\Scripts\activate; pip install -r requirements.txt; cd ..; python run_backend.py
Second terminal: cd frontend; npm install; npm run dev
Open http://localhost:3000
Two caveats to flag:

I verified Python syntax (py_compile clean) but could not run npm install or pip install here, so the first run on Windows will be the real test.
The original anomaly_processing_agent.py imports a trigger_anamoly_dag module that isn't in the repo — the backend bypasses that entirely and uses backend/airflow_trigger.py instead, so nothing depends on the missing file anymore.

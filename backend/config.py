"""Central configuration for the Anomaly Agent backend.

All secrets and environment-specific values live here. Override via environment
variables or a local .env file at the project root.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# --- LLM ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
OPENAI_TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0"))

# --- Database ---
DB_URI = os.getenv(
    "DB_URI",
    "mysql+pymysql://kishore:Gpohealth!#!@dev-db-test.c969yoyq9cyy.us-east-1.rds.amazonaws.com:3306/joblog_metadata",
)

# --- Anomaly domain tables ---
METADATA_TABLE = os.getenv("METADATA_TABLE", "anomaly_metadata")
ANOMALY_TABLE = os.getenv("ANOMALY_TABLE", "anomaly.duplicate_ap_invoice")
COLUMN_INFO_TABLE = os.getenv("COLUMN_INFO_TABLE", "table_column_info")
ANOMALY_TABLE_NAME = os.getenv("ANOMALY_TABLE_NAME", "duplicate_ap_invoice")

# --- Airflow SSH trigger ---
UBUNTU_HOST = os.getenv("UBUNTU_HOST", "ubuntu@172.31.25.132")
SSH_KEY_PATH = os.getenv("SSH_KEY_PATH", r"C:\Users\kkishore\Desktop\Cust_t0004 1.pem")
AIRFLOW_CMD = os.getenv(
    "AIRFLOW_CMD",
    "/home/ubuntu/run_airflow.sh dags trigger execute_adminFee_Data_Pipeline_v1",
)

# --- HTTP / server ---
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))

# --- Paths ---
PROMPTS_DIR = BASE_DIR / "prompts"

# --- Proxy bypass ---
os.environ.setdefault("NO_PROXY", "172.31.27.7")
os.environ.setdefault("no_proxy", "172.31.27.7")
if OPENAI_API_KEY:
    os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

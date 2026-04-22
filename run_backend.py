"""Startup script for the Anomaly Agent backend (Uvicorn with --reload)."""
import os
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"

# Make `import main`, `import database`, etc. work without a package.
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("PYTHONUNBUFFERED", "1")

if __name__ == "__main__":
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=True,
        reload_dirs=[str(BACKEND_DIR), str(ROOT / "prompts")],
    )

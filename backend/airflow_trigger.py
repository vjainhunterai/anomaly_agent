"""SSH-based Airflow DAG trigger (Paramiko)."""
from __future__ import annotations

import logging
from dataclasses import dataclass

import paramiko

from config import AIRFLOW_CMD, SSH_KEY_PATH, UBUNTU_HOST

log = logging.getLogger(__name__)


@dataclass
class TriggerResult:
    ok: bool
    stdout: str
    stderr: str


def trigger_airflow_dag(run_id: str) -> TriggerResult:
    """Run the remote Airflow DAG trigger command over SSH."""
    if "@" not in UBUNTU_HOST:
        return TriggerResult(False, "", f"Invalid UBUNTU_HOST: {UBUNTU_HOST}")
    user, host = UBUNTU_HOST.split("@", 1)
    cmd = f"{AIRFLOW_CMD} --run-id {run_id}"

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(hostname=host, username=user, key_filename=SSH_KEY_PATH, timeout=15)
        _stdin, stdout, stderr = client.exec_command(cmd, timeout=60)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        rc = stdout.channel.recv_exit_status()
        return TriggerResult(ok=rc == 0, stdout=out, stderr=err)
    except Exception as exc:
        log.exception("Airflow trigger failed")
        return TriggerResult(ok=False, stdout="", stderr=str(exc))
    finally:
        client.close()

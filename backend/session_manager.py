"""In-memory session store for the step-based chat agent.

The chat panel drives a small state machine in the backend. Each session is
keyed by UUID and records the user's in-progress date range plus conversation
history. This mirrors the AdminFee agent's approach (plain Python dict, no
LangGraph) so the UI can stay thin.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


# Step identifiers for the agent FSM
STEP_GREET = "greet"
STEP_AWAIT_DATES = "await_dates"
STEP_CONFIRM = "confirm"
STEP_PROCESSING = "processing"
STEP_DONE = "done"
STEP_ERROR = "error"


@dataclass
class ChatTurn:
    role: str  # "user" | "assistant"
    content: str
    ts: float = field(default_factory=time.time)


@dataclass
class Session:
    session_id: str
    step: str = STEP_GREET
    start_date: str | None = None
    end_date: str | None = None
    history: list[ChatTurn] = field(default_factory=list)
    airflow_run_id: str | None = None
    airflow_status: str | None = None  # "pending" | "triggered" | "failed"
    last_error: str | None = None
    analysis: dict[str, Any] = field(default_factory=dict)  # cache for analyst panel
    audit: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.updated_at = time.time()

    def add_turn(self, role: str, content: str) -> None:
        self.history.append(ChatTurn(role=role, content=content))
        self.touch()

    def log(self, event: str, detail: dict[str, Any] | None = None) -> None:
        self.audit.append(
            {"ts": time.time(), "event": event, "detail": detail or {}}
        )


class SessionStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, Session] = {}

    def create(self) -> Session:
        sid = uuid.uuid4().hex
        sess = Session(session_id=sid)
        with self._lock:
            self._sessions[sid] = sess
        return sess

    def get(self, session_id: str) -> Session | None:
        with self._lock:
            return self._sessions.get(session_id)

    def require(self, session_id: str) -> Session:
        sess = self.get(session_id)
        if sess is None:
            raise KeyError(f"Unknown session: {session_id}")
        return sess

    def reset(self, session_id: str) -> Session:
        with self._lock:
            self._sessions.pop(session_id, None)
        return self.create()

    def all_audit(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        with self._lock:
            for s in self._sessions.values():
                for entry in s.audit:
                    out.append({"session_id": s.session_id, **entry})
        out.sort(key=lambda e: e["ts"], reverse=True)
        return out

    def latest(self) -> "Session | None":
        with self._lock:
            if not self._sessions:
                return None
            return max(self._sessions.values(), key=lambda s: s.updated_at)


# module-level singleton
store = SessionStore()

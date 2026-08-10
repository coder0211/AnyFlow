"""A SQLite-backed SessionStore for long-running / multi-process servers.

`InMemorySessionStore` loses sessions when the process exits and cannot be
shared across processes. This store persists each session as a JSON blob in a
SQLite file and opens the database in WAL mode so several server processes can
read concurrently (with SQLite's single-writer locking) against one file.

Only the stdlib `sqlite3` is used — no extra dependency.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from anyflow.core import Session, SessionStore
from anyflow.core.models import SessionStatus, StepResult, StepStatus

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id      TEXT PRIMARY KEY,
    flow_id TEXT NOT NULL,
    status  TEXT NOT NULL,
    data    TEXT NOT NULL
)
"""


def _dump(session: Session) -> str:
    """Serialize the parts of a Session that aren't already columns."""
    return json.dumps(
        {
            "current_step_id": session.current_step_id,
            "variables": session.variables,
            "path": session.path,
            "attempts": session.attempts,
            "history": {
                step_id: {
                    "step_id": r.step_id,
                    "status": r.status.value,
                    "summary": r.summary,
                    "artifacts": r.artifacts,
                }
                for step_id, r in session.history.items()
            },
        }
    )


def _load(row: sqlite3.Row) -> Session:
    data = json.loads(row["data"])
    history = {
        step_id: StepResult(
            step_id=r["step_id"],
            status=StepStatus(r["status"]),
            summary=r["summary"],
            artifacts=r["artifacts"],
        )
        for step_id, r in data["history"].items()
    }
    return Session(
        id=row["id"],
        flow_id=row["flow_id"],
        current_step_id=data["current_step_id"],
        status=SessionStatus(row["status"]),
        history=history,
        variables=data["variables"],
        path=data.get("path", []),
        attempts=data.get("attempts", {}),
    )


class SqliteSessionStore(SessionStore):
    """Persist sessions in a SQLite database file (or ``:memory:``)."""

    def __init__(self, path: str | Path = "anyflow_sessions.db") -> None:
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # WAL lets multiple processes read while one writes.
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def save(self, session: Session) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO sessions (id, flow_id, status, data) VALUES (?, ?, ?, ?)",
            (session.id, session.flow_id, session.status.value, _dump(session)),
        )
        self._conn.commit()

    def load(self, session_id: str) -> Session:
        row = self._conn.execute(
            "SELECT id, flow_id, status, data FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown session {session_id!r}")
        return _load(row)

    def list_sessions(self) -> list[Session]:
        # INSERT OR REPLACE re-inserts on every save, so rowid tracks last-touched
        # — DESC puts the most recently active sessions first (handy for resume).
        rows = self._conn.execute(
            "SELECT id, flow_id, status, data FROM sessions ORDER BY rowid DESC"
        ).fetchall()
        return [_load(row) for row in rows]

    def close(self) -> None:
        self._conn.close()

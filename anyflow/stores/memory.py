"""In-memory session store — the zero-config default.

Keeps sessions in a dict. Perfect for a single-process stdio server, tests, and
demos. State is lost when the process exits and cannot be shared across
processes — use `SqliteSessionStore` for those.
"""

from __future__ import annotations

from anyflow.core import Session, SessionStore


class InMemorySessionStore(SessionStore):
    """A dict-backed `SessionStore`."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def save(self, session: Session) -> None:
        self._sessions[session.id] = session

    def load(self, session_id: str) -> Session:
        try:
            return self._sessions[session_id]
        except KeyError:
            raise KeyError(f"unknown session {session_id!r}") from None

    def list_sessions(self) -> list[Session]:
        # Newest last is insertion order; reverse so recent sessions lead.
        return list(reversed(self._sessions.values()))

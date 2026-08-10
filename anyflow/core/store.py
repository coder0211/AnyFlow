"""The SessionStore interface — the persistence seam for sessions.

The engine (`SessionManager`) depends only on this ABC. Concrete stores live in
`anyflow.stores` (in-memory, SQLite, …), so `anyflow.core` carries no storage
implementation and no storage dependencies. Composition happens at the edges:
the server (and tests) choose which store to hand the manager.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .session import Session


class SessionStore(ABC):
    """Where sessions live. Implement `save`/`load` for a new backend."""

    @abstractmethod
    def save(self, session: Session) -> None:
        """Persist a new or updated session."""

    @abstractmethod
    def load(self, session_id: str) -> Session:
        """Return the session, or raise KeyError if it is unknown."""

    @abstractmethod
    def list_sessions(self) -> list[Session]:
        """Return all stored sessions (order is up to the store)."""

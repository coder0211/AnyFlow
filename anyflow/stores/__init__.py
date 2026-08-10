"""SessionStore implementations.

The `SessionStore` contract lives in `anyflow.core`; every concrete backend lives
here. `InMemorySessionStore` is the zero-config default; `SqliteSessionStore`
persists across restarts and processes.
"""

from .memory import InMemorySessionStore
from .sqlite import SqliteSessionStore

__all__ = ["InMemorySessionStore", "SqliteSessionStore"]

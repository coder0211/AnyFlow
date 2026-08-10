"""Tests for the SQLite session store, including cross-process durability."""

from __future__ import annotations

import pytest
from anyflow.core import SessionManager, SessionStatus, StepResult, StepStatus
from anyflow.flows import build_registry
from anyflow.stores import SqliteSessionStore


def test_round_trip_preserves_state(tmp_path) -> None:
    store = SqliteSessionStore(tmp_path / "s.db")
    sessions = SessionManager(build_registry(), store=store)

    session, _ = sessions.start("refactor-python")
    sessions.complete_step(
        session.id,
        StepResult(
            step_id="analyze",
            status=StepStatus.COMPLETED,
            summary="foo.py:1 smell",
            artifacts={"note": "found it"},
        ),
    )

    loaded = store.load(session.id)
    assert loaded.current_step_id == "plan"
    assert loaded.status is SessionStatus.RUNNING
    assert loaded.history["analyze"].summary == "foo.py:1 smell"
    assert loaded.history["analyze"].artifacts == {"note": "found it"}
    assert loaded.history["analyze"].status is StepStatus.COMPLETED
    store.close()


def test_survives_reopen_and_second_process_view(tmp_path) -> None:
    db = tmp_path / "s.db"
    store_a = SqliteSessionStore(db)
    sessions = SessionManager(build_registry(), store=store_a)
    session, _ = sessions.start("fix-bug")
    store_a.close()

    # A separate store instance (stand-in for another process) sees the session.
    store_b = SqliteSessionStore(db)
    reopened = store_b.load(session.id)
    assert reopened.flow_id == "fix-bug"
    assert reopened.current_step_id == "reproduce"
    store_b.close()


def test_unknown_session_raises(tmp_path) -> None:
    store = SqliteSessionStore(tmp_path / "s.db")
    with pytest.raises(KeyError, match="unknown session"):
        store.load("does-not-exist")
    store.close()

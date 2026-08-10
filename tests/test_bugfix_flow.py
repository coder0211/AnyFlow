"""Tests for the branching bug-fix flow and the session store abstraction."""

from __future__ import annotations

from anyflow.core import (
    SessionManager,
    SessionStatus,
    SessionStore,
    StepResult,
    StepStatus,
)
from anyflow.flows import build_registry
from anyflow.stores import InMemorySessionStore


def _sessions(store: SessionStore | None = None) -> SessionManager:
    return SessionManager(build_registry(), store=store or InMemorySessionStore())


def test_bugfix_happy_path_is_linear() -> None:
    sessions = _sessions()
    session, _ = sessions.start("fix-bug")
    for step_id in ("reproduce", "locate", "fix", "verify"):
        assert session.current_step_id == step_id
        sessions.complete_step(
            session.id,
            StepResult(step_id=step_id, status=StepStatus.COMPLETED, summary="ok"),
        )
    assert session.status is SessionStatus.COMPLETED


def test_failed_verify_routes_back_to_locate() -> None:
    sessions = _sessions()
    session, _ = sessions.start("fix-bug")
    for step_id in ("reproduce", "locate", "fix"):
        sessions.complete_step(
            session.id,
            StepResult(step_id=step_id, status=StepStatus.COMPLETED, summary="ok"),
        )
    assert session.current_step_id == "verify"

    # Verification fails -> the flow loops back to locate, not to completion.
    sessions.complete_step(
        session.id,
        StepResult(step_id="verify", status=StepStatus.FAILED, summary="still red"),
    )
    assert session.status is SessionStatus.RUNNING
    assert session.current_step_id == "locate"


def test_retry_guidance_mentions_previous_failure() -> None:
    sessions = _sessions()
    session, flow = sessions.start("fix-bug")
    for step_id in ("reproduce", "locate", "fix"):
        sessions.complete_step(
            session.id,
            StepResult(step_id=step_id, status=StepStatus.COMPLETED, summary="ok"),
        )
    sessions.complete_step(
        session.id,
        StepResult(step_id="verify", status=StepStatus.FAILED, summary="assertion X"),
    )
    guidance = flow.guide("locate", session.context())
    assert "retry" in guidance.instructions.lower()
    assert "assertion X" in guidance.instructions


def test_session_store_is_swappable() -> None:
    # A custom store proves SessionManager depends only on the interface.
    saved: dict[str, object] = {}

    class RecordingStore(InMemorySessionStore):
        def save(self, session) -> None:  # type: ignore[override]
            saved[session.id] = session
            super().save(session)

    sessions = _sessions(store=RecordingStore())
    session, _ = sessions.start("fix-bug")
    assert session.id in saved
    sessions.complete_step(
        session.id,
        StepResult(step_id="reproduce", status=StepStatus.COMPLETED, summary="ok"),
    )
    # save() called again after advancing.
    assert saved[session.id].current_step_id == "locate"

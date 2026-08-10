"""Tests for the session observability + safety additions:

  * live progress (step N of M, path, per-step attempts),
  * the per-step retry ceiling (loop guard),
  * enumerating sessions to resume them.

These exercise the engine directly; the same data is what the MCP tools return.
"""

from __future__ import annotations

import pytest
from anyflow.core import (
    Flow,
    FlowContext,
    FlowRegistry,
    SessionManager,
    SessionStatus,
    Step,
    StepGuidance,
    StepResult,
    StepStatus,
)
from anyflow.flows import build_registry
from anyflow.stores import InMemorySessionStore, SqliteSessionStore


@pytest.fixture
def sessions() -> SessionManager:
    return SessionManager(build_registry(), InMemorySessionStore())


def _complete(sessions: SessionManager, session_id: str, step_id: str, status="completed"):
    return sessions.complete_step(
        session_id,
        StepResult(step_id=step_id, status=StepStatus(status), summary="done"),
    )


# -- progress --------------------------------------------------------------


def test_progress_tracks_position_and_percent(sessions: SessionManager) -> None:
    session, _ = sessions.start("refactor-python")  # analyze -> plan -> apply

    p = sessions.progress(session)
    assert (p.current_step_id, p.current_index, p.total_steps) == ("analyze", 1, 3)
    assert p.percent == 0
    assert p.completed_steps == []
    assert p.remaining_steps == ["plan", "apply"]
    assert p.path == ["analyze"]
    assert p.attempts == {"analyze": 1}

    _complete(sessions, session.id, "analyze")
    p = sessions.progress(session)
    assert p.current_step_id == "plan"
    assert p.current_index == 2
    assert p.percent == 33
    assert p.completed_steps == ["analyze"]
    assert p.path == ["analyze", "plan"]


def test_progress_records_a_loop_in_the_path(sessions: SessionManager) -> None:
    # fix-bug: reproduce -> locate -> fix -> verify, and a failed verify -> locate.
    session, _ = sessions.start("fix-bug")
    _complete(sessions, session.id, "reproduce")
    _complete(sessions, session.id, "locate")
    _complete(sessions, session.id, "fix")
    _complete(sessions, session.id, "verify", status="failed")  # routes back to locate

    p = sessions.progress(session)
    assert p.current_step_id == "locate"
    assert p.attempts["locate"] == 2  # entered twice
    assert p.path == ["reproduce", "locate", "fix", "verify", "locate"]


# -- loop guard ------------------------------------------------------------


class _Ping(Step):
    id = "ping"
    title = "Ping"
    max_attempts = 2

    def guide(self, context: FlowContext) -> StepGuidance:
        return StepGuidance(step_id=self.id, title=self.title, instructions="ping")


class _Pong(Step):
    id = "pong"
    title = "Pong"

    def guide(self, context: FlowContext) -> StepGuidance:
        return StepGuidance(step_id=self.id, title=self.title, instructions="pong")

    def route(self, result: StepResult, context: FlowContext) -> str | None:
        return "ping"  # always bounce back — an infinite loop without a guard


class _LoopFlow(Flow):
    id = "loop-test"
    name = "Loop test"
    goal = "exercise the retry ceiling"
    steps = [_Ping, _Pong]


def _loop_sessions() -> SessionManager:
    registry = FlowRegistry()
    registry.register(_LoopFlow())
    return SessionManager(registry, InMemorySessionStore())


def test_loop_guard_stops_a_runaway_gate() -> None:
    sessions = _loop_sessions()
    session, _ = sessions.start("loop-test")  # enters ping (attempt 1)

    _complete(sessions, session.id, "ping")  # -> pong
    _complete(sessions, session.id, "pong")  # routes back to ping (attempt 2)
    _complete(sessions, session.id, "ping")  # -> pong

    # pong now routes to ping a 3rd time — over the ceiling of 2.
    with pytest.raises(ValueError, match="retry limit"):
        _complete(sessions, session.id, "pong")

    # The failed advance leaves the session parked, not corrupted, so the agent
    # can inspect history and abort/escalate.
    parked = sessions.get(session.id)
    assert parked.current_step_id == "pong"
    assert parked.status is SessionStatus.RUNNING
    assert sessions.progress(parked).attempts["ping"] == 2


def test_release_patch_has_a_ceiling() -> None:
    # The shipped runbook caps its re-patch loop so it can't ping-pong forever.
    flow = build_registry().get("ship-hotfix")
    assert flow.get_step("patch").max_attempts == 3
    # ...and hands off gracefully instead of raising when it does.
    assert flow.get_step("patch").on_exhausted == "escalate"


class _PingEscalate(Step):
    id = "ping"
    title = "Ping"
    max_attempts = 2
    on_exhausted = "bail"  # route here instead of raising when the ceiling trips

    def guide(self, context: FlowContext) -> StepGuidance:
        return StepGuidance(step_id=self.id, title=self.title, instructions="ping")


class _Bail(Step):
    id = "bail"
    title = "Bail"

    def guide(self, context: FlowContext) -> StepGuidance:
        return StepGuidance(step_id=self.id, title=self.title, instructions="bail")

    def route(self, result: StepResult, context: FlowContext) -> str | None:
        return Flow.END


class _EscalateFlow(Flow):
    id = "escalate-test"
    name = "Escalate test"
    goal = "exercise on_exhausted graceful routing"
    steps = [_PingEscalate, _Pong, _Bail]


def test_on_exhausted_routes_to_escalation_instead_of_raising() -> None:
    registry = FlowRegistry()
    registry.register(_EscalateFlow())
    sessions = SessionManager(registry, InMemorySessionStore())
    session, _ = sessions.start("escalate-test")  # ping (attempt 1)

    _complete(sessions, session.id, "ping")  # -> pong
    _complete(sessions, session.id, "pong")  # routes back to ping (attempt 2)
    _complete(sessions, session.id, "ping")  # -> pong

    # pong routes to ping a 3rd time (over the ceiling) -> hands off to `bail`,
    # no exception, session stays healthy.
    advanced = _complete(sessions, session.id, "pong")
    assert advanced.current_step_id == "bail"
    assert advanced.status is SessionStatus.RUNNING
    assert sessions.progress(advanced).path[-1] == "bail"


# -- listing / resume ------------------------------------------------------


def test_list_sessions_filters_by_status(sessions: SessionManager) -> None:
    a, _ = sessions.start("refactor-python")
    b, _ = sessions.start("fix-bug")
    sessions.abort(b.id)

    running = sessions.list_sessions(SessionStatus.RUNNING)
    assert [s.session_id for s in running] == [a.id]
    assert running[0].flow_id == "refactor-python"
    assert running[0].current_step_id == "analyze"

    aborted = sessions.list_sessions(SessionStatus.ABORTED)
    assert [s.session_id for s in aborted] == [b.id]

    assert {s.session_id for s in sessions.list_sessions()} == {a.id, b.id}


def test_list_sessions_reports_completed_count(sessions: SessionManager) -> None:
    session, _ = sessions.start("refactor-python")
    _complete(sessions, session.id, "analyze")
    (summary,) = sessions.list_sessions(SessionStatus.RUNNING)
    assert summary.steps_completed == 1


def test_sqlite_persists_path_and_attempts_for_resume(tmp_path) -> None:
    db = tmp_path / "s.db"
    sessions = SessionManager(build_registry(), SqliteSessionStore(db))
    session, _ = sessions.start("fix-bug")
    _complete(sessions, session.id, "reproduce")
    _complete(sessions, session.id, "locate")
    _complete(sessions, session.id, "fix")
    _complete(sessions, session.id, "verify", status="failed")  # loop back to locate

    # A fresh manager (stand-in for another process) can list and resume.
    reopened = SessionManager(build_registry(), SqliteSessionStore(db))
    (summary,) = reopened.list_sessions(SessionStatus.RUNNING)
    assert summary.session_id == session.id
    resumed = reopened.progress(reopened.get(session.id))
    assert resumed.current_step_id == "locate"
    assert resumed.attempts["locate"] == 2
    assert resumed.path[-1] == "locate"

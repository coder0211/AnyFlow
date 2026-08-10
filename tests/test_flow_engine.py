"""End-to-end tests for the core engine and the example flow.

These are also the *contract* a new flow should satisfy: a plan that lists its
steps, guidance per step, validation that rejects bad results, and a session
that advances to completion.
"""

from __future__ import annotations

import pytest
from anyflow.core import (
    FlowContext,
    FlowRegistry,
    SessionManager,
    SessionStatus,
    StepResult,
    StepStatus,
)
from anyflow.flows import build_registry
from anyflow.flows.refactor import RefactorPythonFlow
from anyflow.stores import InMemorySessionStore


@pytest.fixture
def registry() -> FlowRegistry:
    return build_registry()


@pytest.fixture
def sessions(registry: FlowRegistry) -> SessionManager:
    return SessionManager(registry, InMemorySessionStore())


def test_registry_loads_builtin_flows(registry: FlowRegistry) -> None:
    assert "refactor-python" in registry
    assert isinstance(registry.get("refactor-python"), RefactorPythonFlow)


def test_plan_lists_all_steps() -> None:
    plan = RefactorPythonFlow().plan()
    assert [s.id for s in plan.steps] == ["analyze", "plan", "apply"]
    assert plan.goal
    assert plan.success_criteria


def test_guidance_is_dynamic_from_context() -> None:
    flow = RefactorPythonFlow()
    ctx = FlowContext(flow_id=flow.id, session_id="s", variables={"target": "foo.py"})
    guidance = flow.guide("analyze", ctx)
    assert "foo.py" in guidance.instructions


def test_plan_step_references_prior_findings() -> None:
    flow = RefactorPythonFlow()
    ctx = FlowContext(flow_id=flow.id, session_id="s")
    ctx.history["analyze"] = StepResult(
        step_id="analyze",
        status=StepStatus.COMPLETED,
        summary="foo.py:10 long function",
    )
    guidance = flow.guide("plan", ctx)
    assert "foo.py:10 long function" in guidance.instructions


def test_full_session_run_to_completion(sessions: SessionManager) -> None:
    session, flow = sessions.start("refactor-python")
    assert session.status is SessionStatus.RUNNING
    assert session.current_step_id == "analyze"

    for step_id in ("analyze", "plan", "apply"):
        assert session.current_step_id == step_id
        sessions.complete_step(
            session.id,
            StepResult(step_id=step_id, status=StepStatus.COMPLETED, summary="done"),
        )

    assert session.status is SessionStatus.COMPLETED
    assert session.current_step_id is None


def test_validation_rejects_empty_analyze_summary(sessions: SessionManager) -> None:
    session, _ = sessions.start("refactor-python")
    with pytest.raises(ValueError, match="findings summary"):
        sessions.complete_step(
            session.id,
            StepResult(step_id="analyze", status=StepStatus.COMPLETED, summary="  "),
        )
    # Session did not advance.
    assert session.current_step_id == "analyze"


def test_complete_step_rejects_wrong_step(sessions: SessionManager) -> None:
    session, _ = sessions.start("refactor-python")
    with pytest.raises(ValueError, match="current step"):
        sessions.complete_step(
            session.id,
            StepResult(step_id="apply", status=StepStatus.COMPLETED, summary="x"),
        )


def test_cannot_complete_after_finished(sessions: SessionManager) -> None:
    session, _ = sessions.start("refactor-python")
    sessions.abort(session.id)
    assert session.status is SessionStatus.ABORTED
    with pytest.raises(ValueError, match="aborted"):
        sessions.complete_step(
            session.id,
            StepResult(step_id="analyze", status=StepStatus.COMPLETED, summary="x"),
        )


def test_unknown_flow_and_session_raise(sessions: SessionManager) -> None:
    with pytest.raises(KeyError, match="unknown flow"):
        sessions.start("nope")
    with pytest.raises(KeyError, match="unknown session"):
        sessions.get("nope")

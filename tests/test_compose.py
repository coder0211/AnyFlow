"""Tests for sub-flow composition: a Flow may embed other Flows in `steps`.

A nested flow is flattened in place, so flows reuse flows. Ids stay unique across
the composition, a sub-flow's internal branching keeps working, and a sub-flow's
`Flow.END` means "finish this sub-flow" — the composite continues at the step
after it (or ends, if the sub-flow is last).
"""

from __future__ import annotations

import pytest
from anyflow.core import (
    Flow,
    SessionManager,
    SessionStatus,
    Step,
    StepGuidance,
    StepResult,
    StepStatus,
)
from anyflow.flows import build_registry
from anyflow.flows.bugfix import FixBugFlow
from anyflow.flows.refactor import RefactorPythonFlow
from anyflow.stores import InMemorySessionStore


def _step(step_id: str, *, route_to: str | None = None) -> type[Step]:
    body: dict = {
        "id": step_id,
        "title": step_id.title(),
        "guide": lambda self, context: StepGuidance(
            step_id=self.id, title=self.title, instructions=step_id
        ),
    }
    if route_to is not None:
        body["route"] = lambda self, result, context: route_to
    return type(f"Step_{step_id}", (Step,), body)


class _Prep(Flow):
    id = "prep"
    name = "Prep"
    goal = "prepare"
    steps = [_step("clone"), _step("configure")]


class _Wrap(Flow):
    id = "wrap"
    name = "Wrap"
    goal = "wrap up"
    steps = [_step("notify")]


class _Composite(Flow):
    id = "composite"
    name = "Composite"
    goal = "prep + a linear flow + wrap, reusing whole flows"
    steps = [_Prep, RefactorPythonFlow, _Wrap]


def _sessions(*extra: Flow) -> SessionManager:
    registry = build_registry()
    for flow in extra:
        registry.register(flow)
    return SessionManager(registry, InMemorySessionStore())


def _run(sessions: SessionManager, flow_id: str, decide=None) -> list[str]:
    """Drive a flow to completion, returning the visited step ids."""
    session, _ = sessions.start(flow_id)
    visited: list[str] = []
    for _ in range(50):
        sid = session.current_step_id
        if sid is None:
            break
        visited.append(sid)
        status = StepStatus(decide(sid)) if decide else StepStatus.COMPLETED
        session = sessions.complete_step(
            session.id, StepResult(step_id=sid, status=status, summary="ok")
        )
    return visited


def test_composition_flattens_sub_flows_in_order() -> None:
    assert _Composite().step_ids() == ["clone", "configure", "analyze", "plan", "apply", "notify"]


def test_composed_flow_runs_to_completion() -> None:
    sessions = _sessions(_Composite())
    expected = ["clone", "configure", "analyze", "plan", "apply", "notify"]
    assert _run(sessions, "composite") == expected


def test_sub_flow_end_falls_through_to_the_next_part() -> None:
    # FixBugFlow's `verify` routes to Flow.END on success. Composed in the middle,
    # that END must continue to the following part (`notify`), not end everything.
    class _WithBugfix(Flow):
        id = "with-bugfix"
        name = "With bugfix"
        goal = "prep then a bugfix then wrap"
        steps = [_Prep, FixBugFlow, _Wrap]

    sessions = _sessions(_WithBugfix())
    visited = _run(sessions, "with-bugfix")
    assert visited == ["clone", "configure", "reproduce", "locate", "fix", "verify", "notify"]


def test_sub_flow_internal_back_route_survives_composition() -> None:
    # A failed `verify` still routes back to `locate` inside the embedded flow.
    class _WithBugfix(Flow):
        id = "with-bugfix2"
        name = "With bugfix 2"
        goal = "prep then fix"
        steps = [_Prep, FixBugFlow, _Wrap]

    sessions = _sessions(_WithBugfix())
    session, _ = sessions.start("with-bugfix2")
    for step_id in ("clone", "configure", "reproduce", "locate", "fix"):
        sessions.complete_step(
            session.id, StepResult(step_id=step_id, status=StepStatus.COMPLETED, summary="ok")
        )
    sessions.complete_step(
        session.id, StepResult(step_id="verify", status=StepStatus.FAILED, summary="still red")
    )
    assert session.current_step_id == "locate"  # routed back inside the sub-flow


def test_early_end_in_a_sub_flow_skips_the_rest_of_that_sub_flow() -> None:
    # A *non-last* step routing END exits its whole sub-flow early, landing on the
    # step after the sub-flow — not the next step inside it.
    class _EarlyExit(Flow):
        id = "early"
        name = "Early"
        goal = "exit early"
        steps = [_step("a", route_to=Flow.END), _step("b")]  # `a` bails before `b`

    class _Outer(Flow):
        id = "outer"
        name = "Outer"
        goal = "early-exit sub-flow then wrap"
        steps = [_EarlyExit, _Wrap]

    sessions = _sessions(_Outer())
    assert _run(sessions, "outer") == ["a", "notify"]  # `b` skipped, fell through to wrap


def test_top_level_end_still_ends_the_flow() -> None:
    # END at the top level (a standalone flow) still finishes it.
    sessions = _sessions()
    session, _ = sessions.start("fix-bug")
    for step_id in ("reproduce", "locate", "fix", "verify"):
        session = sessions.complete_step(
            session.id, StepResult(step_id=step_id, status=StepStatus.COMPLETED, summary="ok")
        )
    assert session.status is SessionStatus.COMPLETED
    assert session.current_step_id is None


def test_duplicate_ids_across_composition_are_rejected() -> None:
    class _Dup(Flow):
        id = "dup"
        name = "Dup"
        goal = "collide"
        steps = [FixBugFlow, FixBugFlow]

    with pytest.raises(TypeError, match="duplicate step id"):
        _Dup()


def test_non_step_non_flow_entry_is_rejected() -> None:
    class _Bad(Flow):
        id = "bad"
        name = "Bad"
        goal = "invalid entry"
        steps = [_step("ok"), object]  # type: ignore[list-item]

    with pytest.raises(TypeError, match="must be Step or Flow"):
        _Bad()

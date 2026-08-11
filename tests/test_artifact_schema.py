"""Tests for declarative artifact schemas (Step.artifact_schema).

The engine checks presence + JSON type before a step's `validate` runs, so a
wrong-typed artifact is rejected with a consistent message and steps don't
hand-roll isinstance boilerplate.
"""

from __future__ import annotations

import pytest
from anyflow.core import (
    FlowContext,
    SessionManager,
    Step,
    StepGuidance,
    StepResult,
    StepStatus,
)
from anyflow.flows import build_registry
from anyflow.stores import InMemorySessionStore


class _Schemad(Step):
    id = "s"
    title = "Schema step"
    artifact_schema = {"count": int, "tags": list, "meta": dict}

    def guide(self, context: FlowContext) -> StepGuidance:
        return StepGuidance(step_id=self.id, title=self.title, instructions="x")


def test_validate_schema_reports_missing_and_mistyped() -> None:
    step = _Schemad()

    ok = step.validate_schema(
        StepResult(
            step_id="s",
            status=StepStatus.COMPLETED,
            artifacts={"count": 3, "tags": [], "meta": {}},
        )
    )
    assert ok.ok

    bad = step.validate_schema(
        StepResult(step_id="s", status=StepStatus.COMPLETED, artifacts={"count": "3", "tags": {}})
    )
    assert not bad.ok
    joined = "; ".join(bad.issues)
    assert "count" in joined and "must be int" in joined
    assert "tags" in joined and "must be list" in joined
    assert "missing required artifact 'meta'" in joined


class _Nested(Step):
    id = "n"
    title = "Nested"
    # object of {passed:int, failed:int} plus a list of strings
    artifact_schema = {"results": {"passed": int, "failed": int}, "files": [str]}

    def guide(self, context: FlowContext) -> StepGuidance:
        return StepGuidance(step_id=self.id, title=self.title, instructions="x")


def _n(artifacts: dict) -> StepResult:
    return StepResult(step_id="n", status=StepStatus.COMPLETED, artifacts=artifacts)


def test_nested_object_and_typed_list_pass() -> None:
    ok = _Nested().validate_schema(
        _n({"results": {"passed": 5, "failed": 0}, "files": ["a.py", "b.py"]})
    )
    assert ok.ok


def test_nested_field_type_error_is_reported_with_a_path() -> None:
    bad = _Nested().validate_schema(
        _n({"results": {"passed": 5, "failed": "none"}, "files": ["a.py"]})
    )
    assert not bad.ok
    assert any("results.failed must be int" in i for i in bad.issues)


def test_missing_nested_field_is_reported() -> None:
    bad = _Nested().validate_schema(_n({"results": {"passed": 5}, "files": []}))
    assert not bad.ok
    assert any("results.failed is required" in i for i in bad.issues)


def test_typed_list_item_error_is_reported_with_index() -> None:
    bad = _Nested().validate_schema(
        _n({"results": {"passed": 1, "failed": 0}, "files": ["a.py", 7]})
    )
    assert not bad.ok
    assert any("files[1] must be str" in i for i in bad.issues)


def test_no_schema_is_a_noop() -> None:
    class _Bare(Step):
        id = "b"
        title = "Bare"

        def guide(self, context: FlowContext) -> StepGuidance:
            return StepGuidance(step_id=self.id, title=self.title, instructions="x")

    assert _Bare().validate_schema(StepResult(step_id="b", status=StepStatus.COMPLETED)).ok


# -- enforced by the engine, before validate -------------------------------


def _drive_to_test(sessions: SessionManager) -> str:
    session, _ = sessions.start("ship-hotfix")
    for step_id in ("triage", "reproduce", "patch"):
        sessions.complete_step(
            session.id, StepResult(step_id=step_id, status=StepStatus.COMPLETED, summary="ok")
        )
    assert sessions.get(session.id).current_step_id == "test"
    return session.id


def test_engine_rejects_wrong_typed_artifact_before_validate() -> None:
    sessions = SessionManager(build_registry(), InMemorySessionStore())
    sid = _drive_to_test(sessions)
    # `test` declares results as a nested object — a string is rejected by the
    # schema, and the message comes from schema enforcement, not the step's validate.
    with pytest.raises(ValueError, match="results must be an object"):
        sessions.complete_step(
            sid,
            StepResult(
                step_id="test",
                status=StepStatus.COMPLETED,
                summary="green",
                artifacts={"results": "all good"},
            ),
        )
    assert sessions.get(sid).current_step_id == "test"  # did not advance

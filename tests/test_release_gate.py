"""Tests for the hardened `deploy_prod` gate — the "gate with teeth" example.

The point: a free-text summary claiming the deploy is done is NOT enough. The
irreversible step is gated on structured artifacts the agent must actually
produce (the prod deploy id and the rollback command, captured verbatim).
"""

from __future__ import annotations

from anyflow.core import FlowContext, StepResult, StepStatus
from anyflow.flows.release.steps import DeployProdStep, TestStep


def _result(**artifacts: str) -> StepResult:
    return StepResult(
        step_id="deploy_prod",
        status=StepStatus.COMPLETED,
        summary="Shipped to prod, 10% canary. Rollback is ready, trust me.",
        artifacts=artifacts,
    )


def _ctx() -> FlowContext:
    return FlowContext(flow_id="ship-hotfix", session_id="s")


def test_prose_alone_is_rejected() -> None:
    v = DeployProdStep().validate(_result(), _ctx())
    assert not v.ok
    assert any("prod_deploy_id" in i for i in v.issues)
    assert any("rollback_command" in i for i in v.issues)


def test_missing_rollback_command_is_rejected() -> None:
    v = DeployProdStep().validate(_result(prod_deploy_id="prod-4490"), _ctx())
    assert not v.ok
    assert any("rollback_command" in i for i in v.issues)


def test_blank_artifact_does_not_count() -> None:
    v = DeployProdStep().validate(
        _result(prod_deploy_id="prod-4490", rollback_command="   "), _ctx()
    )
    assert not v.ok


def test_both_artifacts_present_passes() -> None:
    v = DeployProdStep().validate(
        _result(prod_deploy_id="prod-4490", rollback_command="deploy rollback prod-4489"),
        _ctx(),
    )
    assert v.ok


# -- structured (JSON) artifacts: the `test` step gates on the numbers ---------


def _test_result(results: object) -> StepResult:
    return StepResult(
        step_id="test",
        status=StepStatus.COMPLETED,
        summary="suite is green, added test_regression",
        artifacts={"results": results},
    )


def test_missing_results_artifact_is_rejected_by_schema() -> None:
    v = TestStep().validate_schema(StepResult(step_id="test", status=StepStatus.COMPLETED))
    assert not v.ok
    assert any("results" in i for i in v.issues)


def test_non_integer_counts_are_rejected_by_schema() -> None:
    # The nested schema {"results": {"passed": int, "failed": int}} catches this.
    v = TestStep().validate_schema(_test_result({"passed": "lots", "failed": 0}))
    assert not v.ok
    assert any("results.passed must be int" in i for i in v.issues)


def test_missing_nested_count_is_rejected_by_schema() -> None:
    v = TestStep().validate_schema(_test_result({"passed": 3}))
    assert not v.ok
    assert any("results.failed is required" in i for i in v.issues)


def test_any_failing_test_is_rejected() -> None:
    v = TestStep().validate(_test_result({"passed": 42, "failed": 1}), _ctx())
    assert not v.ok
    assert any("failing" in i for i in v.issues)


def test_zero_tests_run_is_rejected() -> None:
    v = TestStep().validate(_test_result({"passed": 0, "failed": 0}), _ctx())
    assert not v.ok


def test_green_suite_passes() -> None:
    v = TestStep().validate(_test_result({"passed": 43, "failed": 0}), _ctx())
    assert v.ok

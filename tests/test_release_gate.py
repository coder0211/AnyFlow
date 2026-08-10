"""Tests for the hardened `deploy_prod` gate — the "gate with teeth" example.

The point: a free-text summary claiming the deploy is done is NOT enough. The
irreversible step is gated on structured artifacts the agent must actually
produce (the prod deploy id and the rollback command, captured verbatim).
"""

from __future__ import annotations

from anyflow.core import FlowContext, StepResult, StepStatus
from anyflow.flows.release.steps import DeployProdStep


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

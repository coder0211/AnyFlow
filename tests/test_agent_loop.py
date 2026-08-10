"""Eval: does a scripted agent actually drive the MCP loop correctly?

These run the *real* MCP tools (list/plan/start/complete_step) via an in-process
agent and assert the loop holds — including both branch points of the hotfix
runbook (retry-on-staging-failure and rollback-on-regression). This is the
evidence that the guide-and-step-back design works end to end, not just that the
data models serialize.
"""

from __future__ import annotations

import asyncio

from anyflow.server import mcp

from helpers.agent_sim import run_agent


def _always_ok(step_id: str, attempt: int) -> tuple[str, str]:
    return "completed", f"did {step_id}"


def test_linear_flow_runs_to_completion() -> None:
    t = asyncio.run(run_agent(mcp, "refactor-python", _always_ok))
    assert t.completed
    assert t.visited == ["analyze", "plan", "apply"]


def test_hotfix_happy_path_reaches_prod_and_monitors() -> None:
    t = asyncio.run(run_agent(mcp, "ship-hotfix", _always_ok))
    assert t.completed
    # Reached production and monitoring, and never touched the rollback path.
    assert t.visited[-2:] == ["deploy_prod", "monitor"]
    assert "rollback" not in t.visited


def test_staging_failure_routes_back_to_patch_before_prod() -> None:
    def decide(step_id: str, attempt: int) -> tuple[str, str]:
        # Fail staging verification once, then succeed.
        if step_id == "verify_staging" and attempt == 0:
            return "failed", "still broken on staging"
        return "completed", f"did {step_id}"

    t = asyncio.run(run_agent(mcp, "ship-hotfix", decide))
    assert t.completed
    # The gate held: patch ran twice and prod only came after the 2nd verify.
    assert t.visited.count("patch") == 2
    assert t.visited.count("verify_staging") == 2
    assert t.visited.index("deploy_prod") > t.visited.index("verify_staging")
    # Crucially, prod was NOT reached on the first (failed) verify.
    first_verify = t.visited.index("verify_staging")
    assert "deploy_prod" not in t.visited[: first_verify + 1]


def test_prod_regression_routes_to_rollback() -> None:
    def decide(step_id: str, attempt: int) -> tuple[str, str]:
        if step_id == "monitor":
            return "failed", "error rate spiked after rollout"
        return "completed", f"did {step_id}"

    t = asyncio.run(run_agent(mcp, "ship-hotfix", decide))
    assert t.completed
    assert t.visited[-1] == "rollback"
    assert t.visited.index("rollback") > t.visited.index("monitor")

"""Tests for the Verifier seam — independent, out-of-band gate checks.

Proves: core stays pure (the interface is all it defines), a step consults
`context.verify` only when a verifier is injected, and wiring one gives the
deploy_prod gate real teeth (it can reject a deploy the agent *claims* is live).
"""

from __future__ import annotations

import pytest
from anyflow.core import (
    Check,
    SessionManager,
    StepResult,
    StepStatus,
)
from anyflow.flows import build_registry
from anyflow.stores import InMemorySessionStore
from anyflow.verify import FunctionVerifier

# Artifacts the gated steps require on the way to deploy_prod.
TEST_ARTIFACTS = {"results": {"passed": 10, "failed": 0}}
PROD_ARTIFACTS = {"prod_deploy_id": "prod-4490", "rollback_command": "rollback prod-4489"}


def _drive_to_deploy_prod(sessions: SessionManager) -> str:
    """Run ship-hotfix up to (not including) deploy_prod; return the session id."""
    session, _ = sessions.start("ship-hotfix")
    steps = [
        ("triage", {}),
        ("reproduce", {}),
        ("patch", {}),
        ("test", TEST_ARTIFACTS),
        ("deploy_staging", {}),
        ("verify_staging", {}),
    ]
    for step_id, artifacts in steps:
        sessions.complete_step(
            session.id,
            StepResult(
                step_id=step_id,
                status=StepStatus.COMPLETED,
                summary="ok",
                artifacts=artifacts,
            ),
        )
    assert sessions.get(session.id).current_step_id == "deploy_prod"
    return session.id


def _deploy(sessions: SessionManager, sid: str) -> None:
    sessions.complete_step(
        sid,
        StepResult(
            step_id="deploy_prod",
            status=StepStatus.COMPLETED,
            summary="shipped",
            artifacts=PROD_ARTIFACTS,
        ),
    )


# -- the seam itself -------------------------------------------------------


def test_function_verifier_reports_unknown_checks_as_failures() -> None:
    v = FunctionVerifier({"known": lambda **_: Check(True)})
    assert v.verify("known").ok
    unknown = v.verify("nope")
    assert not unknown.ok and "no verifier registered" in unknown.detail


def test_no_verifier_skips_verification_and_ships() -> None:
    # Default composition (no verifier) — the gate falls back to structural checks.
    sessions = SessionManager(build_registry(), InMemorySessionStore())
    sid = _drive_to_deploy_prod(sessions)
    _deploy(sessions, sid)  # must not raise
    assert sessions.get(sid).current_step_id == "monitor"


# -- teeth: a wired verifier can veto a claimed deploy ---------------------


def test_wired_verifier_rejects_a_deploy_that_is_not_live() -> None:
    seen: dict = {}

    def not_live(deploy_id: str) -> Check:
        seen["deploy_id"] = deploy_id
        return Check(False, "deploy id not found in the platform")

    sessions = SessionManager(
        build_registry(),
        InMemorySessionStore(),
        verifier=FunctionVerifier({"prod_deploy_live": not_live}),
    )
    sid = _drive_to_deploy_prod(sessions)
    with pytest.raises(ValueError, match="not confirmed live"):
        _deploy(sessions, sid)
    # The verifier actually received the reported deploy id.
    assert seen["deploy_id"] == "prod-4490"
    # Gate held — still parked on deploy_prod.
    assert sessions.get(sid).current_step_id == "deploy_prod"


def test_wired_verifier_passes_a_live_deploy() -> None:
    sessions = SessionManager(
        build_registry(),
        InMemorySessionStore(),
        verifier=FunctionVerifier({"prod_deploy_live": lambda deploy_id: Check(True, deploy_id)}),
    )
    sid = _drive_to_deploy_prod(sessions)
    _deploy(sessions, sid)  # verifier confirms live -> advances
    assert sessions.get(sid).current_step_id == "monitor"

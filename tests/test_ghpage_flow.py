"""Contract tests for the `github-page` flow.

No network: these exercise the flow's shape and gate through the engine. The
real HTTP fetch + HTML write live in examples/github_page.py.
"""

from __future__ import annotations

import pytest
from anyflow.core import SessionManager, SessionStatus, StepResult, StepStatus
from anyflow.flows import build_registry
from anyflow.flows.ghpage import GithubPageFlow
from anyflow.stores import InMemorySessionStore


@pytest.fixture
def sessions() -> SessionManager:
    return SessionManager(build_registry(), InMemorySessionStore())


def _complete(sessions, sid, step, status="completed", summary="ok"):
    return sessions.complete_step(
        sid, StepResult(step_id=step, status=StepStatus(status), summary=summary)
    )


def test_flow_is_registered_with_expected_steps() -> None:
    flow = build_registry().get("github-page")
    assert isinstance(flow, GithubPageFlow)
    assert [s.id for s in flow.plan().steps] == ["fetch", "build", "preview"]


def test_guidance_mentions_the_source_url() -> None:
    flow = build_registry().get("github-page")
    from anyflow.core import FlowContext

    ctx = FlowContext(
        flow_id=flow.id, session_id="s", variables={"source": "github.com/psf/requests"}
    )
    assert "github.com/psf/requests" in flow.guide("fetch", ctx).instructions


def test_failed_fetch_ends_the_flow(sessions: SessionManager) -> None:
    session, _ = sessions.start("github-page")
    _complete(sessions, session.id, "fetch", status="failed", summary="404 not found")
    # Gate: a dead link stops the flow instead of building an empty page.
    assert session.current_step_id is None
    assert session.status is SessionStatus.COMPLETED


def test_build_step_requires_an_html_path(sessions: SessionManager) -> None:
    session, _ = sessions.start("github-page")
    _complete(sessions, session.id, "fetch", summary="repo psf/requests, 50k stars")
    with pytest.raises(ValueError, match="html"):
        _complete(sessions, session.id, "build", summary="done, no file")
    assert session.current_step_id == "build"  # did not advance


def test_happy_path_reaches_completion(sessions: SessionManager) -> None:
    session, _ = sessions.start("github-page")
    _complete(sessions, session.id, "fetch", summary="repo psf/requests")
    _complete(sessions, session.id, "build", summary="wrote build/psf-requests.html")
    _complete(sessions, session.id, "preview", summary="opened, renders fine")
    assert session.status is SessionStatus.COMPLETED

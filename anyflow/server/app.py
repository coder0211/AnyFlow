"""any-flow MCP server.

Exposes the flow registry over MCP so an agent can: discover flows, read a
flow's plan (progressive disclosure), start a stateful session, and step through
it. The server *guides* — it never runs the agent's work. The agent reads each
`StepGuidance`, does the work with its own tools, then reports back via
`complete_step`, which validates and advances the session.

Run it:  python -m anyflow.server   (stdio transport)
"""

from __future__ import annotations

import os
from dataclasses import asdict

from mcp.server.mcpserver import MCPServer

from anyflow.core import SessionManager, SessionStore, StepResult, StepStatus
from anyflow.flows import build_registry
from anyflow.stores import InMemorySessionStore, SqliteSessionStore

INSTRUCTIONS = """\
any-flow provides step-by-step workflows that guide you through a task.
Typical loop:
  1. list_workflows() to see what's available and when to use each.
  2. get_workflow_plan(workflow_id) to read the overview before committing.
  3. start_workflow(workflow_id) -> a session_id and the first step's guidance.
  4. Do the work the step describes with your own tools.
  5. complete_step(session_id, ...) to report the result and get the next step.
Repeat 4-5 until the flow reports it is complete.
"""

def _build_store() -> SessionStore:
    """Pick a session store from the environment.

    Set ANYFLOW_DB to a file path to persist sessions across restarts and share
    them across processes (SQLite). Unset -> the in-memory default.
    """
    db_path = os.environ.get("ANYFLOW_DB")
    return SqliteSessionStore(db_path) if db_path else InMemorySessionStore()


registry = build_registry()
sessions = SessionManager(registry, store=_build_store())
mcp = MCPServer(name="any-flow", version="0.1.0", instructions=INSTRUCTIONS)


def _guidance(flow_id: str, step_id: str | None, session_id: str) -> dict | None:
    """Build the guidance payload for a step, or None if the flow is done."""
    if step_id is None:
        return None
    flow = registry.get(flow_id)
    session = sessions.get(session_id)
    return asdict(flow.guide(step_id, session.context()))


@mcp.tool()
def list_workflows() -> list[dict]:
    """List every available workflow with its goal and when to use it."""
    return [
        {
            "id": flow.id,
            "name": flow.name,
            "goal": flow.goal,
            "when_to_use": flow.when_to_use,
        }
        for flow in registry.all()
    ]


@mcp.tool()
def get_workflow_plan(workflow_id: str) -> dict:
    """Get a workflow's overview (goal, prerequisites, steps, success criteria).

    Read this before starting so you understand the shape of the work. It does
    not create a session and does not commit you to anything.
    """
    return asdict(registry.get(workflow_id).plan())


@mcp.tool()
def start_workflow(workflow_id: str) -> dict:
    """Start a workflow. Returns a session_id, the plan, and the first step's guidance.

    Keep the session_id — you pass it to every subsequent call.
    """
    session, flow = sessions.start(workflow_id)
    return {
        "session_id": session.id,
        "status": session.status.value,
        "plan": asdict(flow.plan()),
        "current_step": _guidance(flow.id, session.current_step_id, session.id),
    }


@mcp.tool()
def get_current_step(session_id: str) -> dict:
    """Get guidance for the session's current step (re-fetch is safe)."""
    session = sessions.get(session_id)
    return {
        "session_id": session.id,
        "status": session.status.value,
        "current_step": _guidance(session.flow_id, session.current_step_id, session.id),
    }


@mcp.tool()
def complete_step(
    session_id: str,
    step_id: str,
    status: str = "completed",
    summary: str = "",
    artifacts: dict[str, str] | None = None,
) -> dict:
    """Report a step's result and advance the session.

    `step_id` must be the session's current step. `status` is one of
    "completed", "failed", "skipped". The step may validate `summary`/`artifacts`
    and reject the report; fix the issues and call again. On success you get the
    next step's guidance, or a completion marker when the flow is finished.
    """
    result = StepResult(
        step_id=step_id,
        status=StepStatus(status),
        summary=summary,
        artifacts=artifacts or {},
    )
    session = sessions.complete_step(session_id, result)
    return {
        "session_id": session.id,
        "status": session.status.value,
        "next_step": _guidance(session.flow_id, session.current_step_id, session.id),
        "flow_complete": session.current_step_id is None,
    }


@mcp.tool()
def abort_workflow(session_id: str) -> dict:
    """Abandon a session without completing it."""
    session = sessions.abort(session_id)
    return {"session_id": session.id, "status": session.status.value}


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

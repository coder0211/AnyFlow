"""Test helper: a tiny in-process agent that drives a workflow via the MCP tools.

This is deliberately NOT an LLM — the point is to prove the *loop* holds: an
agent that lists a workflow, reads its plan, starts a session, and keeps calling
`complete_step` with the current step id gets walked through the flow correctly,
including branch/retry points. The "agent's decisions" are scripted so the run
is deterministic and assertable in CI (see tests/test_agent_loop.py).

It calls `MCPServer.call_tool` directly (in-process) rather than over stdio, so
it exercises the actual tool functions, session state, and routing logic.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field

from mcp.server.mcpserver import MCPServer

# A decision function: (step_id, attempt_index) -> (status, summary).
Decider = Callable[[str, int], tuple[str, str]]


def _unwrap(result: object) -> dict:
    """Normalize a CallToolResult into the plain dict the tool returned."""
    structured = getattr(result, "structured_content", None)
    if structured is not None:
        # FastMCP wraps a non-dict top-level return under "result".
        return structured.get("result", structured) if isinstance(structured, dict) else structured
    content = getattr(result, "content", None)
    if content:
        return json.loads(content[0].text)
    raise RuntimeError(f"could not unwrap tool result: {result!r}")


@dataclass
class Transcript:
    """A readable record of the agent<->server exchange, for demos and asserts."""

    lines: list[str] = field(default_factory=list)
    visited: list[str] = field(default_factory=list)
    completed: bool = False

    def add(self, line: str) -> None:
        self.lines.append(line)

    def __str__(self) -> str:
        return "\n".join(self.lines)


async def run_agent(
    mcp: MCPServer,
    workflow_id: str,
    decide: Decider,
    *,
    variables: dict[str, str] | None = None,
    artifacts: dict[str, dict[str, str]] | None = None,
    max_steps: int = 50,
) -> Transcript:
    """Drive `workflow_id` to completion using `decide` for each step's result.

    `artifacts` optionally supplies structured artifacts per step id — needed for
    steps whose validation gates on them (e.g. deploy_prod).
    """
    artifacts = artifacts or {}
    t = Transcript()

    async def call(name: str, args: dict) -> dict:
        return _unwrap(await mcp.call_tool(name, args))

    workflows = await call("list_workflows", {})
    picked = next(w for w in workflows if w["id"] == workflow_id)
    t.add(f"🧭 agent: picked workflow '{picked['id']}' — {picked['name']}")

    plan = await call("get_workflow_plan", {"workflow_id": workflow_id})
    t.add(f"📋 plan: {len(plan['steps'])} steps · goal: {plan['goal'][:70]}...")

    started = await call("start_workflow", {"workflow_id": workflow_id})
    session_id = started["session_id"]
    current = started["current_step"]
    t.add(f"▶️  started session {session_id[:8]}…")

    attempts: dict[str, int] = {}
    for _ in range(max_steps):
        if current is None:
            break
        step_id = current["step_id"]
        t.visited.append(step_id)
        attempt = attempts.get(step_id, 0)
        attempts[step_id] = attempt + 1

        t.add(f"\n── step: {current['title']}  ({step_id})")
        t.add(f"   guide: {current['instructions'].splitlines()[0][:88]}")
        status, summary = decide(step_id, attempt)
        flag = "✅" if status == "completed" else "⚠️ "
        t.add(f"   {flag} agent -> {status}: {summary[:80]}")

        advanced = await call(
            "complete_step",
            {
                "session_id": session_id,
                "step_id": step_id,
                "status": status,
                "summary": summary,
                "artifacts": artifacts.get(step_id, {}),
            },
        )
        current = advanced["next_step"]
        if advanced["flow_complete"]:
            t.completed = True
            t.add("\n🎉 flow complete.")
            break
        else:
            t.add(f"   → next: {current['step_id']}")

    return t

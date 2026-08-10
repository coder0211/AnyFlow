"""Self-contained example: drive the ship-hotfix runbook through the MCP tools.

Run it:  python examples/run_demo.py   (or: make demo)

A scripted "agent" starts the workflow and keeps calling `complete_step` with the
current step until the flow finishes. It deliberately FAILS staging verification
once, so you can watch any-flow refuse to advance to production and route the
agent back to `patch` before the gate passes. This is what the committed
docs/demo.svg shows — this script is how you reproduce it.

The point: an agent that just reports each step's result gets walked through the
whole procedure, gates and all. any-flow never runs the work — it only guides.
"""

from __future__ import annotations

import asyncio
import json

from anyflow.server import mcp

# The agent's scripted decisions: step_id -> responses per attempt (status, note).
# verify_staging fails on the first attempt and passes on the retry.
SCRIPT: dict[str, list[tuple[str, str]]] = {
    "triage": [("completed", "SEV2, prod v2.3.1, checkout page 500s. Go: hotfix warranted.")],
    "reproduce": [("completed", "Reproduced on tag v2.3.1: null cart -> 500 at checkout.")],
    "patch": [
        ("completed", "hotfix/checkout-null-cart off v2.3.1: guard empty cart."),
        ("completed", "Re-patched: also handle cart with deleted SKU (missed before)."),
    ],
    "test": [("completed", "Suite green. Added test_checkout_empty_and_deleted_cart.")],
    "deploy_staging": [("completed", "Deployed build #4471 to staging.")],
    "verify_staging": [
        ("failed", "Repro fixed, but smoke test: deleted-SKU cart still 500s."),
        ("completed", "Repro fixed AND smoke tests pass on staging build #4488."),
    ],
    "deploy_prod": [("completed", "Prod deploy prod-4490, 10% canary rollout.")],
    "monitor": [("completed", "15 min: error rate back to 0.02% baseline, latency flat. Stable.")],
    "rollback": [("completed", "Rolled back to prod-4489; metrics recovered.")],
}

# Structured artifacts for the steps whose validation gates on them (a real agent
# would report the actual numbers / ids).
ARTIFACTS: dict[str, dict] = {
    "test": {"results": {"passed": 128, "failed": 0}},
    "deploy_prod": {
        "prod_deploy_id": "prod-4490",
        "rollback_command": "kubectl rollout undo deploy/checkout --to-revision=4489",
    },
}


def _unwrap(result: object) -> dict:
    """Normalize a CallToolResult into the plain dict the tool returned."""
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        return structured.get("result", structured)
    content = getattr(result, "content", None)
    if content:
        return json.loads(content[0].text)
    raise RuntimeError(f"could not unwrap tool result: {result!r}")


async def main() -> None:
    async def call(name: str, args: dict) -> dict:
        return _unwrap(await mcp.call_tool(name, args))

    started = await call("start_workflow", {"workflow_id": "ship-hotfix"})
    session_id = started["session_id"]
    current = started["current_step"]
    print(f"▶️  started ship-hotfix · session {session_id[:8]}…\n")

    attempts: dict[str, int] = {}
    visited: list[str] = []
    while current is not None:
        step_id = current["step_id"]
        visited.append(step_id)
        attempt = attempts.get(step_id, 0)
        attempts[step_id] = attempt + 1

        responses = SCRIPT[step_id]
        status, note = responses[min(attempt, len(responses) - 1)]
        mark = "✅" if status == "completed" else "⚠️ "
        print(f"── {current['title']} ({step_id})")
        print(f"   {mark} {status}: {note}")

        advanced = await call(
            "complete_step",
            {
                "session_id": session_id,
                "step_id": step_id,
                "status": status,
                "summary": note,
                "artifacts": ARTIFACTS.get(step_id, {}),
            },
        )
        p = advanced["progress"]
        print(f"   progress: step {p['current_index']}/{p['total_steps']} · {p['percent']}%")
        current = advanced["next_step"]
        if advanced["flow_complete"]:
            print("\n🎉 flow complete.")
        elif current is not None:
            print(f"   → next: {current['step_id']}\n")

    print(f"\nvisited: {' -> '.join(visited)}")


if __name__ == "__main__":
    asyncio.run(main())

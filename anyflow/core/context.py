"""Execution context passed into a step's guide/validate/route hooks.

A step is *stateless* by itself; everything it needs to make a decision — prior
results, shared variables — arrives through the FlowContext. This keeps flows
pure and easy to test: give a context, assert the guidance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import JsonValue, StepResult
from .verify import Check, Verifier


@dataclass(slots=True)
class FlowContext:
    """Read model of a session, handed to a flow's steps.

    `history` maps step_id -> the result the agent reported for it.
    `variables` is a free-form scratchpad a flow can use to pass data between
    steps (e.g. a file path chosen in step 1 and reused in step 3). Values are
    JSON-serializable — the same structured type as `StepResult.artifacts`.
    `verifier` is an optional out-of-band checker (see `anyflow.core.verify`); a
    step's `validate` may consult it to confirm a claim against reality.
    """

    flow_id: str
    session_id: str
    history: dict[str, StepResult] = field(default_factory=dict)
    variables: dict[str, JsonValue] = field(default_factory=dict)
    verifier: Verifier | None = None

    def result_of(self, step_id: str) -> StepResult | None:
        return self.history.get(step_id)

    def is_completed(self, step_id: str) -> bool:
        result = self.history.get(step_id)
        return result is not None and result.status.value == "completed"

    def verify(self, check: str, **params: Any) -> Check:
        """Run an independent `check`, or skip (treated as ok) if none is wired.

        Lets a step harden a gate *when* an operator has configured a verifier,
        without forcing one: `if not context.verify("x", …).ok: fail`. To require
        verification instead of skipping, test `context.verifier is not None`.
        """
        if self.verifier is None:
            return Check(ok=True, detail="no verifier configured; skipped")
        return self.verifier.verify(check, **params)

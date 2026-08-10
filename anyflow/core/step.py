"""The Step interface — one unit of guidance in a flow.

Implementors override `guide` (required). `validate` and `route` have sensible
defaults (always-valid, linear progression) so simple linear flows stay terse
while branching flows remain expressible.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .context import FlowContext
from .models import StepGuidance, StepResult, Validation


class Step(ABC):
    """A single step. Subclasses set `id`/`title` and implement `guide`."""

    #: Stable identifier, unique within a flow (e.g. "analyze").
    id: str
    #: Human-readable title shown in the plan overview.
    title: str
    #: One-line description used in the flow overview.
    description: str = ""
    #: Loop guard: the most times a session may *enter* this step (via linear
    #: progression or a `route` back into it). None = unlimited. When a branch
    #: would exceed this, the engine refuses to advance and tells the agent to
    #: escalate instead of ping-ponging a gate forever.
    max_attempts: int | None = None
    #: Where the loop guard routes when this step would be entered past
    #: `max_attempts`. Set it to a terminal step id (e.g. "escalate") to hand off
    #: gracefully instead of raising — turns "give up loudly" into "escalate to a
    #: human". None keeps the safe default: refuse to advance and raise.
    on_exhausted: str | None = None

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        # Fail loudly at import time rather than mysteriously at runtime.
        if ABC not in cls.__bases__:
            for attr in ("id", "title"):
                if not getattr(cls, attr, None):
                    raise TypeError(f"{cls.__name__} must define a non-empty `{attr}`")

    @abstractmethod
    def guide(self, context: FlowContext) -> StepGuidance:
        """Return the instruction the agent should follow for this step.

        May inspect `context` (prior results, variables) to tailor guidance.
        """

    def validate(self, result: StepResult, context: FlowContext) -> Validation:
        """Check the agent's reported result. Default: accept anything.

        Override to enforce an output contract (e.g. an artifact must exist).
        """
        return Validation.passed()

    def route(self, result: StepResult, context: FlowContext) -> str | None:
        """Return the next step id, or None to use the flow's default order.

        Override for branching flows. Returning `Flow.END` ends the flow early.
        """
        return None

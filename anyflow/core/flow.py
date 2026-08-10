"""The Flow interface — an ordered graph of steps with a shared goal.

A concrete flow is what contributors clone and implement: subclass `Flow`,
declare metadata and a list of `Step` classes, done. The default linear
progression covers most flows; override `route` on a step for branching.
"""

from __future__ import annotations

from abc import ABC

from .context import FlowContext
from .models import FlowPlan, StepGuidance, StepResult, StepSummary
from .step import Step


class Flow(ABC):
    """A named workflow. Subclasses declare `id`, `name`, `goal`, `steps`."""

    #: Sentinel a step's `route` can return to finish the flow early.
    END: str = "__end__"

    #: Stable identifier (e.g. "refactor-python").
    id: str
    #: Human-readable name.
    name: str
    #: What completing this flow achieves.
    goal: str
    #: A hint for the agent on when to pick this flow over others.
    when_to_use: str = ""
    #: Ordered step classes. Order defines default linear progression.
    steps: list[type[Step]] = []
    #: Things that must be true before starting.
    prerequisites: list[str] = []
    #: How the agent knows the whole flow succeeded.
    success_criteria: list[str] = []

    def __init__(self) -> None:
        if not self.steps:
            raise TypeError(f"{type(self).__name__} must declare at least one step")
        self._steps: list[Step] = [cls() for cls in self.steps]
        self._by_id: dict[str, Step] = {}
        for step in self._steps:
            if step.id in self._by_id:
                raise TypeError(f"duplicate step id {step.id!r} in flow {self.id!r}")
            self._by_id[step.id] = step

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if ABC not in cls.__bases__:
            for attr in ("id", "name", "goal"):
                if not getattr(cls, attr, None):
                    raise TypeError(f"{cls.__name__} must define a non-empty `{attr}`")

    # -- introspection -----------------------------------------------------

    def plan(self) -> FlowPlan:
        """Build the overview an agent reads before executing."""
        return FlowPlan(
            flow_id=self.id,
            name=self.name,
            goal=self.goal,
            when_to_use=self.when_to_use,
            steps=[
                StepSummary(id=s.id, title=s.title, description=s.description)
                for s in self._steps
            ],
            prerequisites=list(self.prerequisites),
            success_criteria=list(self.success_criteria),
        )

    def first_step_id(self) -> str:
        return self._steps[0].id

    def step_ids(self) -> list[str]:
        """Step ids in declared (default linear) order."""
        return [s.id for s in self._steps]

    def get_step(self, step_id: str) -> Step:
        try:
            return self._by_id[step_id]
        except KeyError:
            raise KeyError(f"unknown step {step_id!r} in flow {self.id!r}") from None

    def guide(self, step_id: str, context: FlowContext) -> StepGuidance:
        return self.get_step(step_id).guide(context)

    # -- progression -------------------------------------------------------

    def next_step_id(self, step_id: str, result: StepResult, context: FlowContext) -> str | None:
        """Resolve the next step: an explicit `route`, else linear order.

        Returns None when the flow is complete.
        """
        step = self.get_step(step_id)
        routed = step.route(result, context)
        if routed == self.END:
            return None
        if routed is not None:
            # Validate the target exists so branching typos fail fast.
            self.get_step(routed)
            return routed
        # Default: the next step in declared order.
        order = [s.id for s in self._steps]
        idx = order.index(step_id)
        return order[idx + 1] if idx + 1 < len(order) else None

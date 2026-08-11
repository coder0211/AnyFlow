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


def _first_step_id(entries: list[type[Step] | type[Flow]]) -> str | None:
    """The id of the first actual step reachable from `entries`, or None."""
    for entry in entries:
        if isinstance(entry, type) and issubclass(entry, Flow):
            found = _first_step_id(list(entry.steps))
            if found is not None:
                return found
        elif isinstance(entry, type) and issubclass(entry, Step):
            return entry.id
    return None


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
    #: Ordered entries defining default linear progression. Each is a `Step`
    #: subclass, or another `Flow` subclass to **compose** — a nested flow is
    #: flattened in place (its steps spliced here, in order), so flows reuse
    #: flows. Ids must stay unique across the composition; a sub-flow's `route`
    #: targets keep working because the ids are preserved, and a sub-flow's
    #: `Flow.END` means "finish this sub-flow" — the composite continues at the
    #: step after it (or ends, if the sub-flow is last).
    steps: list[type[Step] | type[Flow]] = []
    #: Things that must be true before starting.
    prerequisites: list[str] = []
    #: How the agent knows the whole flow succeeded.
    success_criteria: list[str] = []

    def __init__(self) -> None:
        if not self.steps:
            raise TypeError(f"{type(self).__name__} must declare at least one step")
        # Flatten entries (Steps and composed sub-flows) into one ordered list,
        # and record, per step, where `Flow.END` leads: for a top-level step that
        # is the whole flow's end (None); for a step inside a composed sub-flow,
        # the step right after that sub-flow — so a sub-flow's END means "finish
        # this sub-flow", not "finish everything".
        self._steps: list[Step] = []
        self._end_target: dict[str, str | None] = {}
        self._flatten(list(self.steps), escape=None)
        if not self._steps:
            raise TypeError(f"{type(self).__name__} composed to zero steps")
        self._by_id: dict[str, Step] = {}
        for step in self._steps:
            if step.id in self._by_id:
                raise TypeError(f"duplicate step id {step.id!r} in flow {self.id!r}")
            self._by_id[step.id] = step

    def _flatten(self, entries: list[type[Step] | type[Flow]], escape: str | None) -> None:
        """Append `entries`' steps to `self._steps`, recording END targets.

        `escape` is where an `END` occurring in this sequence's steps should go
        (the step following this whole sequence at the enclosing level, or None
        for the top level). Sub-flows recurse with their own follower as escape.
        """
        for i, entry in enumerate(entries):
            follower = _first_step_id(entries[i + 1 :]) or escape
            if isinstance(entry, type) and issubclass(entry, Flow):
                self._flatten(list(entry.steps), escape=follower)
            elif isinstance(entry, type) and issubclass(entry, Step):
                step = entry()
                self._steps.append(step)
                self._end_target[step.id] = escape
            else:
                raise TypeError(
                    f"{type(self).__name__}.steps entries must be Step or Flow "
                    f"subclasses, got {entry!r}"
                )

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
            # Ends the flow (None) at top level, or falls through to the step
            # after the enclosing sub-flow when this step was composed in.
            return self._end_target.get(step_id)
        if routed is not None:
            # Validate the target exists so branching typos fail fast.
            self.get_step(routed)
            return routed
        # Default: the next step in declared order.
        order = [s.id for s in self._steps]
        idx = order.index(step_id)
        return order[idx + 1] if idx + 1 < len(order) else None

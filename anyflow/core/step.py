"""The Step interface — one unit of guidance in a flow.

Implementors override `guide` (required). `validate` and `route` have sensible
defaults (always-valid, linear progression) so simple linear flows stay terse
while branching flows remain expressible.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

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
    #: Declarative artifact contract, checked by the engine *before* `validate`
    #: runs, so steps skip isinstance boilerplate and get consistent errors. Maps
    #: a required artifact key to a spec, which is one of:
    #:   * a JSON type — ``str``, ``int``, ``float``, ``bool``, ``list``, ``dict``
    #:   * a nested dict of specs — ``{"passed": int, "failed": int}`` (an object)
    #:   * a one-element list — ``[str]`` (a list whose every item matches)
    #: specs nest arbitrarily, e.g. ``{"results": {"cases": [str]}}``. None = no
    #: schema. (Note: ``bool`` is a subclass of ``int`` in Python.)
    artifact_schema: dict[str, Any] | None = None

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

    def validate_schema(self, result: StepResult) -> Validation:
        """Check reported artifacts against `artifact_schema` (presence + shape).

        Not meant to be overridden — the engine calls it before `validate`. It is
        a no-op unless the step declares `artifact_schema`, and recurses into
        nested object/list specs.
        """
        schema = self.artifact_schema
        if not schema:
            return Validation.passed()
        issues: list[str] = []
        for key, spec in schema.items():
            if key not in result.artifacts:
                issues.append(f"missing required artifact {key!r}")
            else:
                issues.extend(_schema_issues(result.artifacts[key], spec, key))
        return Validation.passed() if not issues else Validation(ok=False, issues=issues)

    def validate(self, result: StepResult, context: FlowContext) -> Validation:
        """Check the agent's reported result. Default: accept anything.

        Override to enforce an output contract (e.g. an artifact must exist).
        Runs *after* `validate_schema`, so if you declared `artifact_schema` you
        can assume the listed artifacts are present and correctly typed.
        """
        return Validation.passed()

    def route(self, result: StepResult, context: FlowContext) -> str | None:
        """Return the next step id, or None to use the flow's default order.

        Override for branching flows. Returning `Flow.END` ends the flow early.
        """
        return None


def _schema_issues(value: Any, spec: Any, path: str) -> list[str]:
    """Recursively check `value` against an `artifact_schema` `spec`."""
    if isinstance(spec, type):
        if not isinstance(value, spec):
            return [f"{path} must be {spec.__name__}, got {type(value).__name__}"]
        return []
    if isinstance(spec, dict):
        if not isinstance(value, dict):
            return [f"{path} must be an object, got {type(value).__name__}"]
        issues: list[str] = []
        for key, sub in spec.items():
            if key not in value:
                issues.append(f"{path}.{key} is required")
            else:
                issues.extend(_schema_issues(value[key], sub, f"{path}.{key}"))
        return issues
    if isinstance(spec, list) and len(spec) == 1:
        if not isinstance(value, list):
            return [f"{path} must be a list, got {type(value).__name__}"]
        issues = []
        for i, item in enumerate(value):
            issues.extend(_schema_issues(item, spec[0], f"{path}[{i}]"))
        return issues
    raise TypeError(f"invalid artifact_schema spec at {path!r}: {spec!r}")

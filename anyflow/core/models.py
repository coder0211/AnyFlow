"""Data contracts shared across the any-flow core.

These models are the *wire format* between the MCP server and an AI agent.
They intentionally carry natural-language guidance (not executable logic):
any-flow *guides* an agent, it does not run the agent's work for it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class StepStatus(StrEnum):
    """Outcome an agent reports after attempting a step."""

    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class SessionStatus(StrEnum):
    """Lifecycle state of a running workflow session."""

    RUNNING = "running"
    COMPLETED = "completed"
    ABORTED = "aborted"


@dataclass(frozen=True, slots=True)
class StepSummary:
    """One line of a workflow overview — cheap, high-level, for planning."""

    id: str
    title: str
    description: str


@dataclass(frozen=True, slots=True)
class FlowPlan:
    """The overview an agent reads *before* executing — progressive disclosure.

    Keep this small: it is fetched up front so the agent understands the shape
    of the work without paying for every step's full guidance.
    """

    flow_id: str
    name: str
    goal: str
    when_to_use: str
    steps: list[StepSummary]
    prerequisites: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class StepGuidance:
    """Detailed instruction for a single step, fetched only when reached.

    This is the heart of the "guide for AI" idea: the fields tell the agent
    *what to do*, *what it needs*, *which tools to reach for*, and *how to know
    it succeeded* — then the agent does the actual work with its own tools.
    """

    step_id: str
    title: str
    instructions: str
    inputs_required: list[str] = field(default_factory=list)
    suggested_tools: list[str] = field(default_factory=list)
    output_contract: str = ""
    validation: list[str] = field(default_factory=list)
    is_last: bool = False


@dataclass(frozen=True, slots=True)
class StepResult:
    """What an agent reports back after attempting a step."""

    step_id: str
    status: StepStatus
    summary: str = ""
    artifacts: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Validation:
    """Result of checking a StepResult against a step's expectations."""

    ok: bool
    issues: list[str] = field(default_factory=list)

    @classmethod
    def passed(cls) -> Validation:
        return cls(ok=True)

    @classmethod
    def failed(cls, *issues: str) -> Validation:
        return cls(ok=False, issues=list(issues))

"""any-flow core: the interfaces every flow implements against.

The core is deliberately dependency-free (no `mcp` import) so flows and their
contract tests run without a server. The MCP layer lives in `anyflow.server`.
"""

from .context import FlowContext
from .flow import Flow
from .models import (
    FlowPlan,
    FlowProgress,
    JsonValue,
    SessionStatus,
    SessionSummary,
    StepGuidance,
    StepResult,
    StepStatus,
    StepSummary,
    Validation,
)
from .registry import FlowRegistry
from .session import Session, SessionManager
from .step import Step
from .store import SessionStore
from .verify import Check, Verifier

__all__ = [
    "Check",
    "Flow",
    "FlowContext",
    "FlowPlan",
    "FlowProgress",
    "FlowRegistry",
    "JsonValue",
    "Session",
    "SessionManager",
    "SessionStatus",
    "SessionStore",
    "SessionSummary",
    "Step",
    "StepGuidance",
    "StepResult",
    "StepStatus",
    "StepSummary",
    "Validation",
    "Verifier",
]

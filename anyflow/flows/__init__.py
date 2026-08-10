"""Built-in flows shipped with any-flow.

To add a flow: implement it (see `refactor` as a template), then add one
`registry.register(...)` line below. That single edit is the whole registration
story — no import-time magic, no plugin scanning.
"""

from __future__ import annotations

from anyflow.core import FlowRegistry

from .bugfix import FixBugFlow
from .ghpage import GithubPageFlow
from .refactor import RefactorPythonFlow
from .release import ShipHotfixFlow


def load_builtin_flows(registry: FlowRegistry) -> FlowRegistry:
    """Register every built-in flow into `registry` and return it."""
    registry.register(ShipHotfixFlow())
    registry.register(GithubPageFlow())
    registry.register(RefactorPythonFlow())
    registry.register(FixBugFlow())
    return registry


def build_registry() -> FlowRegistry:
    """Convenience: a fresh registry preloaded with the built-in flows."""
    return load_builtin_flows(FlowRegistry())

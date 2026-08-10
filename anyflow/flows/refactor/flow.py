"""The example "refactor a Python module" flow.

Copy this directory as a template for your own flow: declare metadata, list the
step classes in execution order, and register the flow in
`anyflow.flows.load_builtin_flows`.
"""

from __future__ import annotations

from anyflow.core import Flow

from .steps import AnalyzeStep, ApplyStep, PlanStep


class RefactorPythonFlow(Flow):
    id = "refactor-python"
    name = "Refactor a Python module"
    goal = "Improve a module's readability and structure without changing behaviour."
    when_to_use = (
        "Use when the user asks to clean up, refactor, or improve a specific "
        "Python file and behaviour must be preserved."
    )
    steps = [AnalyzeStep, PlanStep, ApplyStep]
    prerequisites = [
        "The target module path is known.",
        "A way to verify behaviour exists (tests, or a manual smoke check).",
    ]
    success_criteria = [
        "The module is easier to read and its behaviour is unchanged.",
        "Verification (tests/smoke check) passed after the edits.",
    ]

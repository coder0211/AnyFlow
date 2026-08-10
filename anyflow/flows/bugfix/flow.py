"""The example "fix a bug" flow — demonstrates a branching retry loop."""

from __future__ import annotations

from anyflow.core import Flow

from .steps import FixStep, LocateStep, ReproduceStep, VerifyStep


class FixBugFlow(Flow):
    id = "fix-bug"
    name = "Fix a bug"
    goal = "Diagnose and fix a reported bug, with a regression test proving it."
    when_to_use = (
        "Use when the user reports something is broken and wants it fixed with a "
        "test that guards against regressions."
    )
    steps = [ReproduceStep, LocateStep, FixStep, VerifyStep]
    prerequisites = [
        "A bug report describing expected vs actual behaviour.",
        "A runnable test suite (or a way to run the repro).",
    ]
    success_criteria = [
        "The reproduction no longer fails.",
        "The full test suite passes, including a new regression test.",
    ]

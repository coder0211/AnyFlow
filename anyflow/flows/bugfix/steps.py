"""Steps for the example "fix a bug" flow.

Unlike the linear refactor flow, this one *branches*: if verification fails, the
`verify` step routes back to `locate` instead of ending. This is the reference
for how a flow expresses a retry loop via `Step.route`.
"""

from __future__ import annotations

from anyflow.core import (
    Flow,
    FlowContext,
    Step,
    StepGuidance,
    StepResult,
    StepStatus,
    Validation,
)


class ReproduceStep(Step):
    id = "reproduce"
    title = "Reproduce the bug"
    description = "Get a reliable, minimal reproduction before touching any code."

    def guide(self, context: FlowContext) -> StepGuidance:
        report = context.variables.get("report", "the reported behaviour")
        return StepGuidance(
            step_id=self.id,
            title=self.title,
            instructions=(
                f"Reproduce {report}. Write the smallest command or failing test "
                "that shows the bug. Do NOT attempt a fix yet — first prove you "
                "can trigger the bug on demand."
            ),
            inputs_required=["Bug report / expected vs actual behaviour"],
            suggested_tools=["run tests (pytest)", "run the app"],
            output_contract="The exact repro command and the observed failure output.",
            validation=["A concrete repro (command or failing test) is captured."],
        )

    def validate(self, result: StepResult, context: FlowContext) -> Validation:
        if not result.summary.strip():
            return Validation.failed("Need the repro command and observed failure.")
        return Validation.passed()


class LocateStep(Step):
    id = "locate"
    title = "Locate the root cause"
    description = "Trace the failure to the specific code responsible."

    def guide(self, context: FlowContext) -> StepGuidance:
        prior = context.result_of("verify")
        retry_note = (
            "This is a retry: the previous fix did not pass verification —\n"
            f"{prior.summary}\nRe-examine your assumption about the root cause.\n\n"
            if prior and prior.status is StepStatus.FAILED
            else ""
        )
        return StepGuidance(
            step_id=self.id,
            title=self.title,
            instructions=(
                f"{retry_note}Starting from the repro, trace the failure to the "
                "exact function/line responsible. State the root cause in one "
                "sentence before proposing any change."
            ),
            inputs_required=["A working reproduction"],
            suggested_tools=["read_file / Read", "grep / search", "debugger / logging"],
            output_contract="A file:line pointer to the root cause and a one-line diagnosis.",
            validation=["Root cause is pinned to a specific location, not guessed."],
        )


class FixStep(Step):
    id = "fix"
    title = "Apply the fix"
    description = "Make the smallest change that addresses the root cause."

    def guide(self, context: FlowContext) -> StepGuidance:
        cause = context.result_of("locate")
        cause_note = f"Root cause identified:\n{cause.summary}\n\n" if cause else ""
        return StepGuidance(
            step_id=self.id,
            title=self.title,
            instructions=(
                f"{cause_note}Make the smallest change that fixes the root cause. "
                "Avoid unrelated cleanup. Add or update a test that would have "
                "caught this bug."
            ),
            inputs_required=["The identified root cause"],
            suggested_tools=["edit / Edit"],
            output_contract="The diff applied and the test added/updated.",
            validation=["Change is scoped to the root cause.", "A regression test exists."],
        )


class VerifyStep(Step):
    id = "verify"
    title = "Verify the fix"
    description = "Run the repro and the full suite; loop back if it still fails."

    def guide(self, context: FlowContext) -> StepGuidance:
        return StepGuidance(
            step_id=self.id,
            title=self.title,
            instructions=(
                "Run the original repro and the full test suite. Report status="
                "'completed' only if the repro no longer fails AND the suite is "
                "green. If anything still fails, report status='failed' with the "
                "output — the flow will send you back to re-diagnose."
            ),
            inputs_required=["The applied fix"],
            suggested_tools=["run tests (pytest)"],
            output_contract="Pass/fail of the repro and the suite, with output.",
            validation=["The repro was re-run and the suite result is reported."],
            is_last=True,
        )

    def route(self, result: StepResult, context: FlowContext) -> str | None:
        # Retry loop: a failed verification sends the agent back to re-diagnose.
        if result.status is StepStatus.FAILED:
            return "locate"
        return Flow.END

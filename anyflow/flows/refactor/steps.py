"""Steps for the example "refactor a Python module" flow.

This file is the reference for what a real flow looks like: each Step returns
natural-language guidance for the agent, reads prior results from the context,
and (where it matters) validates what the agent reports back.
"""

from __future__ import annotations

from anyflow.core import FlowContext, Step, StepGuidance, StepResult, Validation


class AnalyzeStep(Step):
    id = "analyze"
    title = "Analyze the target module"
    description = "Read the code and catalogue concrete refactoring opportunities."

    def guide(self, context: FlowContext) -> StepGuidance:
        target = context.variables.get("target", "the module the user named")
        return StepGuidance(
            step_id=self.id,
            title=self.title,
            instructions=(
                f"Read {target} in full. Identify concrete code smells: long "
                "functions, duplicated logic, unclear names, missing types, "
                "dead code. Do NOT change anything yet — only observe."
            ),
            inputs_required=["Path to the module to refactor"],
            suggested_tools=["read_file / Read", "grep / search"],
            output_contract=(
                "A bullet list of findings, each with a file:line reference and "
                "a one-line description of the smell."
            ),
            validation=["At least one finding is reported with a file:line ref."],
        )

    def validate(self, result: StepResult, context: FlowContext) -> Validation:
        if not result.summary.strip():
            return Validation.failed("Analyze step needs a non-empty findings summary.")
        return Validation.passed()


class PlanStep(Step):
    id = "plan"
    title = "Draft a refactoring plan"
    description = "Turn findings into an ordered, low-risk sequence of edits."

    def guide(self, context: FlowContext) -> StepGuidance:
        findings = context.result_of("analyze")
        findings_note = (
            f"Based on your analysis:\n{findings.summary}\n\n"
            if findings and findings.summary
            else ""
        )
        return StepGuidance(
            step_id=self.id,
            title=self.title,
            instructions=(
                f"{findings_note}Propose an ordered plan of small, independently "
                "verifiable edits. Put behaviour-preserving changes first and "
                "flag anything that could alter behaviour. Keep each edit "
                "reviewable on its own."
            ),
            inputs_required=["Findings from the analyze step"],
            suggested_tools=[],
            output_contract="A numbered list of edits, each scoped to one change.",
            validation=["The plan references the findings and orders edits by risk."],
        )


class ApplyStep(Step):
    id = "apply"
    title = "Apply the plan and verify"
    description = "Make the edits one at a time and confirm behaviour is preserved."

    def guide(self, context: FlowContext) -> StepGuidance:
        return StepGuidance(
            step_id=self.id,
            title=self.title,
            instructions=(
                "Apply the planned edits one at a time. After each edit, run the "
                "test suite (or a smoke check if none exists). Stop and report if "
                "any check fails rather than pressing on."
            ),
            inputs_required=["The refactoring plan from the previous step"],
            suggested_tools=["edit / Edit", "run tests (pytest)"],
            output_contract=(
                "A summary of edits made and the result of the verification run."
            ),
            validation=[
                "Every planned edit is either applied or explicitly deferred.",
                "Tests were run and their outcome is reported.",
            ],
            is_last=True,
        )

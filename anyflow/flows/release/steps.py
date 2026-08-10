"""Steps for the "ship a hotfix to production" runbook.

This is the flagship flow: a real multi-tool release runbook with hard gates and
two branch points. It is exactly the kind of procedure an unguided agent tends
to short-cut — skipping staging verification, forgetting a rollback plan, or
declaring victory before watching production metrics. The flow makes the gates
non-optional.

Branches (via `Step.route`):
  * verify_staging FAILED  -> back to `patch` (the fix was wrong; re-do it)
  * monitor FAILED         -> `rollback` (a regression slipped to prod)
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


class TriageStep(Step):
    id = "triage"
    title = "Triage the incident"
    description = "Confirm severity and that a hotfix (not the normal release) is warranted."

    def guide(self, context: FlowContext) -> StepGuidance:
        incident = context.variables.get("incident", "the reported incident")
        return StepGuidance(
            step_id=self.id,
            title=self.title,
            instructions=(
                f"Assess {incident}: user impact, blast radius, and whether it is "
                "urgent enough to bypass the normal release train. Record severity "
                "(SEV1-3) and the affected version. If it is NOT hotfix-worthy, say "
                "so — the operator should stop here and schedule a normal fix."
            ),
            inputs_required=["Incident report / alert", "Current production version"],
            suggested_tools=["incident tracker (Jira/PagerDuty)", "logs / dashboards"],
            output_contract="Severity, affected version, and a go/no-go decision with reasoning.",
            validation=["Severity and affected version are stated.", "Go/no-go is explicit."],
        )

    def validate(self, result: StepResult, context: FlowContext) -> Validation:
        if not result.summary.strip():
            return Validation.failed("Triage needs severity, version, and a go/no-go decision.")
        return Validation.passed()


class ReproduceStep(Step):
    id = "reproduce"
    title = "Reproduce on the released version"
    description = "Prove the bug on the exact version running in production."

    def guide(self, context: FlowContext) -> StepGuidance:
        return StepGuidance(
            step_id=self.id,
            title=self.title,
            instructions=(
                "Check out the production tag/version and reproduce the failure "
                "there — not on main. Capture the exact steps and observed error. "
                "A hotfix built against the wrong baseline is worse than no hotfix."
            ),
            inputs_required=["Affected version from triage"],
            suggested_tools=["git checkout <tag>", "run the app / repro script"],
            output_contract="Repro steps and observed failure on the production version.",
            validation=["The bug was reproduced on the production version specifically."],
        )


class PatchStep(Step):
    id = "patch"
    title = "Write the minimal patch"
    description = "Create a hotfix branch and make the smallest safe change."

    def guide(self, context: FlowContext) -> StepGuidance:
        retry = context.result_of("verify_staging")
        retry_note = (
            "RETRY: staging verification failed last time —\n"
            f"{retry.summary}\nThe previous patch did not resolve the issue. "
            "Re-diagnose before editing again.\n\n"
            if retry and retry.status is StepStatus.FAILED
            else ""
        )
        return StepGuidance(
            step_id=self.id,
            title=self.title,
            instructions=(
                f"{retry_note}Branch from the production tag (e.g. "
                "`git checkout -b hotfix/<id> <tag>`). Make the smallest change "
                "that fixes the root cause — no refactors, no unrelated cleanup. "
                "Scope creep in a hotfix is how one incident becomes two."
            ),
            inputs_required=["Reproduction from the previous step"],
            suggested_tools=["git checkout -b", "edit / Edit"],
            output_contract="A hotfix branch name and the diff applied.",
            validation=[
                "Change is branched from the production tag, not main.",
                "Diff is minimal.",
            ],
        )


class TestStep(Step):
    id = "test"
    title = "Test and add a regression guard"
    description = "Run the suite and add a test that fails without the patch."

    def guide(self, context: FlowContext) -> StepGuidance:
        return StepGuidance(
            step_id=self.id,
            title=self.title,
            instructions=(
                "Run the full test suite on the hotfix branch. Add a regression "
                "test that fails on the old code and passes with the patch — this "
                "is what stops the same incident recurring. Report the suite result."
            ),
            inputs_required=["The applied patch"],
            suggested_tools=["pytest / test runner", "CI pipeline"],
            output_contract="Suite result (green) and the name of the new regression test.",
            validation=[
                "The full suite passed.",
                "A regression test covering this bug was added.",
            ],
        )


class DeployStagingStep(Step):
    id = "deploy_staging"
    title = "Deploy to staging"
    description = "Ship the hotfix branch to the staging environment."

    def guide(self, context: FlowContext) -> StepGuidance:
        return StepGuidance(
            step_id=self.id,
            title=self.title,
            instructions=(
                "Deploy the hotfix branch to staging via the normal pipeline (not "
                "a manual copy). Record the deploy id / build number so you can "
                "verify the right artifact is running."
            ),
            inputs_required=["A green hotfix branch"],
            suggested_tools=["CI/CD (GitHub Actions, Argo, etc.)", "deploy CLI"],
            output_contract="Staging deploy id and confirmation the hotfix build is live there.",
            validation=["A specific staging deploy id is recorded."],
        )


class VerifyStagingStep(Step):
    id = "verify_staging"
    title = "Verify on staging"
    description = "Confirm the original repro is fixed on staging (gate before prod)."

    def guide(self, context: FlowContext) -> StepGuidance:
        return StepGuidance(
            step_id=self.id,
            title=self.title,
            instructions=(
                "Re-run the original reproduction against staging and run a quick "
                "smoke test of the surrounding feature. Report status='completed' "
                "ONLY if the bug is gone and nothing obvious broke. If it still "
                "fails, report status='failed' with details — the flow will send "
                "you back to re-patch. Do NOT proceed to production on a hunch."
            ),
            inputs_required=["Staging deploy id"],
            suggested_tools=["repro script against staging", "smoke tests"],
            output_contract="Pass/fail of the repro on staging plus smoke-test notes.",
            validation=["The original repro was re-run against staging and the result reported."],
        )

    def route(self, result: StepResult, context: FlowContext) -> str | None:
        # A staging failure is a gate: go re-patch instead of shipping to prod.
        if result.status is StepStatus.FAILED:
            return "patch"
        return None  # linear -> deploy_prod


class DeployProdStep(Step):
    id = "deploy_prod"
    title = "Deploy to production"
    description = "Ship to production only after staging is verified green."

    def guide(self, context: FlowContext) -> StepGuidance:
        return StepGuidance(
            step_id=self.id,
            title=self.title,
            instructions=(
                "Deploy the verified hotfix to production. Announce in the incident "
                "channel before you start and when it completes. Prefer a gradual "
                "rollout (canary / percentage) if the platform supports it, and "
                "have the rollback command ready in your clipboard before you ship."
            ),
            inputs_required=["A passing staging verification"],
            suggested_tools=["CI/CD deploy", "incident/Slack channel", "feature flags"],
            output_contract="Production deploy id, rollout strategy, and rollback command on hand.",
            validation=[
                "A production deploy id is recorded.",
                "The rollback command is identified before rollout.",
            ],
        )


class MonitorStep(Step):
    id = "monitor"
    title = "Monitor production"
    description = "Watch error rate and key metrics; roll back on regression."

    def guide(self, context: FlowContext) -> StepGuidance:
        return StepGuidance(
            step_id=self.id,
            title=self.title,
            instructions=(
                "Watch error rate, latency, and the incident's key metric for at "
                "least 10-15 minutes (longer for SEV1). Compare against the "
                "pre-deploy baseline. If metrics regress, report status='failed' — "
                "the flow will route you to rollback. If everything is stable, "
                "report status='completed' to close the runbook."
            ),
            inputs_required=["Production deploy id", "Pre-deploy metric baseline"],
            suggested_tools=["dashboards (Grafana/Datadog)", "error tracker (Sentry)"],
            output_contract="Post-deploy metrics vs baseline and a stable/regressed verdict.",
            validation=["Metrics were compared against a baseline over a stated window."],
            is_last=True,
        )

    def route(self, result: StepResult, context: FlowContext) -> str | None:
        if result.status is StepStatus.FAILED:
            return "rollback"
        return Flow.END


class RollbackStep(Step):
    id = "rollback"
    title = "Roll back"
    description = "Revert production to the last known-good release and regroup."

    def guide(self, context: FlowContext) -> StepGuidance:
        return StepGuidance(
            step_id=self.id,
            title=self.title,
            instructions=(
                "Execute the rollback to the last known-good deploy immediately — "
                "restoring service beats debugging live. Confirm metrics recover, "
                "announce the rollback in the incident channel, and note what "
                "regressed so the next patch attempt can address it."
            ),
            inputs_required=["The rollback command prepared during deploy"],
            suggested_tools=["deploy CLI rollback", "dashboards", "incident channel"],
            output_contract="Confirmation prod is on the known-good version and metrics recovered.",
            validation=["Production is confirmed restored to a known-good state."],
            is_last=True,
        )

    def route(self, result: StepResult, context: FlowContext) -> str | None:
        return Flow.END

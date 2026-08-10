"""The "ship a hotfix to production" runbook flow."""

from __future__ import annotations

from anyflow.core import Flow

from .steps import (
    DeployProdStep,
    DeployStagingStep,
    MonitorStep,
    PatchStep,
    ReproduceStep,
    RollbackStep,
    TestStep,
    TriageStep,
    VerifyStagingStep,
)


class ShipHotfixFlow(Flow):
    id = "ship-hotfix"
    name = "Ship a hotfix to production"
    goal = (
        "Get a verified, minimal fix into production safely — with staging gates, "
        "monitoring, and a rollback path — without skipping steps under pressure."
    )
    when_to_use = (
        "Use during an incident when a fix must reach production faster than the "
        "normal release train, and correctness under pressure matters."
    )
    steps = [
        TriageStep,
        ReproduceStep,
        PatchStep,
        TestStep,
        DeployStagingStep,
        VerifyStagingStep,
        DeployProdStep,
        MonitorStep,
        RollbackStep,
    ]
    prerequisites = [
        "You have deploy access to staging and production.",
        "There is an incident channel and a metrics dashboard to watch.",
        "The production version/tag is known.",
    ]
    success_criteria = [
        "The fix is live in production and the incident metric has recovered,",
        "OR production was safely rolled back to a known-good state.",
        "A regression test guards against the bug recurring.",
    ]

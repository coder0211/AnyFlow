"""Tests for the ready-made verifier checks (anyflow.verify.checks).

Kept offline and deterministic: subprocess exits we control, and an unresolvable
host for the URL check.
"""

from __future__ import annotations

import sys

from anyflow.verify import FunctionVerifier, checks


def test_command_succeeds_on_exit_zero() -> None:
    assert checks.command_succeeds([sys.executable, "-c", "import sys; sys.exit(0)"]).ok


def test_command_fails_on_nonzero_exit() -> None:
    c = checks.command_succeeds([sys.executable, "-c", "import sys; sys.exit(3)"])
    assert not c.ok
    assert "exit 3" in c.detail


def test_command_that_cannot_run_is_a_failure_not_a_crash() -> None:
    c = checks.command_succeeds(["definitely-not-a-real-command-xyz123"])
    assert not c.ok
    assert "failed to run" in c.detail


def test_url_check_reports_unreachable_host_as_failure() -> None:
    # `.invalid` is reserved to never resolve — offline and deterministic.
    c = checks.url_returns_2xx("http://nonexistent.invalid./", timeout=2)
    assert not c.ok
    assert "unreachable" in c.detail


def test_checks_plug_into_a_function_verifier() -> None:
    verifier = FunctionVerifier({"cmd_ok": checks.command_succeeds})
    ok = verifier.verify("cmd_ok", command=[sys.executable, "-c", "import sys; sys.exit(0)"])
    assert ok.ok

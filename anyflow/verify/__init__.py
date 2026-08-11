"""Concrete verifiers — the part that actually reaches out to check a claim.

Kept *outside* `anyflow.core` on purpose: the core defines the `Verifier`
interface and does no I/O, so the engine stays pure. The things that touch the
network, a subprocess, or a database live here and are injected at the
composition root (the server, or your own script):

    from anyflow.core import Check, SessionManager
    from anyflow.verify import FunctionVerifier

    verifier = FunctionVerifier({
        "url_returns_2xx": lambda url: Check(_http_ok(url), url),
    })
    sessions = SessionManager(registry, store, verifier=verifier)

A step's `validate` then calls `context.verify("url_returns_2xx", url=…)`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from anyflow.core import Check, Verifier

from . import checks

__all__ = ["FunctionVerifier", "checks"]


class FunctionVerifier(Verifier):
    """A `Verifier` backed by a registry of named check functions.

    Register only the checks your environment actually supports. An unknown check
    name returns ``Check(ok=False, …)`` (never raises, never silently passes) so a
    typo in a step can't wave a gate through.
    """

    def __init__(self, checks: dict[str, Callable[..., Check]]) -> None:
        self._checks = dict(checks)

    def verify(self, check: str, /, **params: Any) -> Check:
        fn = self._checks.get(check)
        if fn is None:
            return Check(ok=False, detail=f"no verifier registered for {check!r}")
        return fn(**params)

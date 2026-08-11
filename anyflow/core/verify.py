"""Independent, out-of-band verification — turning a claim into a checked fact.

A gate's `validate` normally trusts what the agent *reports*. That enforces
ordering, not truth: an agent can say "staging is green" without it being so. A
`Verifier` closes that gap — it checks a claim against reality (an HTTP probe, a
CI status, a subprocess).

The core defines only this *interface* and performs no I/O of its own, so the
engine stays pure and never executes anything. Concrete verifiers — the things
that actually reach out — live outside core (see `anyflow.verify`) and are
injected at the composition root. A step opts in by consulting `context.verifier`
inside `validate`; if no verifier is wired, verification is simply skipped and
the step falls back to its structural checks.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Check:
    """Outcome of one independent verification."""

    ok: bool
    detail: str = ""


class Verifier(ABC):
    """Checks a named claim against reality. Implemented outside core."""

    @abstractmethod
    def verify(self, check: str, /, **params: Any) -> Check:
        """Run the named `check` with `params`, returning whether it holds.

        `check` is an agreed name the concrete verifier knows how to run (e.g.
        "url_returns_2xx"); `params` are its inputs. Implementations should return
        ``Check(ok=False, …)`` for an unknown check rather than raising, so a typo
        can never silently pass a gate.
        """

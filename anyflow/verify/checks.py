"""Ready-made check functions to register in a `FunctionVerifier`.

These are the batteries: small, stdlib-only checks that turn a step's claim into
an independently verified fact. Register the ones your environment supports —
they're plain ``(**params) -> Check`` callables:

    from anyflow.verify import FunctionVerifier
    from anyflow.verify import checks

    verifier = FunctionVerifier({
        "url_2xx": checks.url_returns_2xx,
        "cmd_ok": checks.command_succeeds,
    })

A step then calls, e.g., ``context.verify("url_2xx", url="https://staging/health")``.
"""

from __future__ import annotations

import subprocess
import urllib.error
import urllib.request

from anyflow.core import Check


def url_returns_2xx(url: str, *, timeout: float = 10.0) -> Check:
    """Check that a GET to `url` returns a 2xx status."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            code = resp.status
    except urllib.error.HTTPError as e:
        return Check(False, f"{url} -> HTTP {e.code}")
    except (urllib.error.URLError, OSError) as e:
        return Check(False, f"{url} unreachable: {e}")
    return Check(200 <= code < 300, f"{url} -> HTTP {code}")


def command_succeeds(command: list[str] | str, *, timeout: float = 60.0) -> Check:
    """Check that `command` exits 0. Pass a list (argv) or a shell string."""
    shell = isinstance(command, str)
    try:
        proc = subprocess.run(
            command,
            shell=shell,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as e:
        return Check(False, f"{command!r} failed to run: {e}")
    if proc.returncode == 0:
        return Check(True, "exit 0")
    return Check(False, f"exit {proc.returncode}: {proc.stderr.strip()[:200]}")

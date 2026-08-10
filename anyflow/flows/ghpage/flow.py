"""The "GitHub link -> HTML page" flow.

The simplest useful end-to-end flow to try: give it a public GitHub URL and it
walks the agent through fetching the public data, building one self-contained
HTML page, and previewing it.
"""

from __future__ import annotations

from anyflow.core import Flow

from .steps import BuildStep, FetchStep, PreviewStep


class GithubPageFlow(Flow):
    id = "github-page"
    name = "Generate an HTML page from a public GitHub link"
    goal = "Turn a public GitHub repo or user URL into one self-contained HTML page."
    when_to_use = (
        "Use when someone gives you a public GitHub link (a repo or a user/org) and "
        "wants a shareable, self-contained HTML page or summary built from it."
    )
    steps = [FetchStep, BuildStep, PreviewStep]
    prerequisites = [
        "A public GitHub URL (a repo like github.com/owner/name, or a user/org).",
        "A way to make HTTP requests and to write and open a file.",
    ]
    success_criteria = [
        "The public GitHub data was fetched (not invented).",
        "A single self-contained HTML file was produced from that data.",
        "The page was previewed and renders correctly.",
    ]

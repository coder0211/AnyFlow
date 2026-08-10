"""Steps for the "GitHub link -> HTML page" flow.

The simplest useful end-to-end flow: hand it a public GitHub URL (a repo or a
user/org) and it walks the agent through fetching the public data, building one
self-contained HTML page from it, and eyeballing the result. It uses only tools
the agent already has — an HTTP fetch, a file write, and a browser/open — and the
public GitHub REST API, which needs no authentication for public data.

One gate: if the link can't be fetched (typo, private, or 404), `fetch` ends the
flow instead of building a page out of nothing.
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


class FetchStep(Step):
    id = "fetch"
    title = "Fetch the public GitHub data"
    description = "Read the repo or user's public info from the GitHub REST API."

    def guide(self, context: FlowContext) -> StepGuidance:
        source = context.variables.get("source", "the GitHub URL the user gave")
        return StepGuidance(
            step_id=self.id,
            title=self.title,
            instructions=(
                f"Parse {source} into either a repo (owner/name) or a user/org "
                "handle, then fetch its PUBLIC data from the GitHub REST API — no "
                "auth or token is needed for public resources:\n"
                "  • Repo: GET https://api.github.com/repos/{owner}/{repo}\n"
                "      → name, description, stargazers_count, forks_count, language,\n"
                "        topics, html_url, homepage, license, owner.avatar_url\n"
                "  • User/org: GET https://api.github.com/users/{login}\n"
                "      → name, bio, avatar_url, public_repos, followers, html_url\n"
                "        (optionally /users/{login}/repos?sort=stars for top repos)\n"
                "If the request 404s or the resource is private, report "
                "status='failed' with the reason — the flow will stop rather than "
                "build a page from nothing. Otherwise report the key fields."
            ),
            inputs_required=["A public GitHub URL (a repo or a user/org)"],
            suggested_tools=["WebFetch / curl", "GitHub REST API (api.github.com)"],
            output_contract=(
                "The key public fields (name, description, stars/repos, language, "
                "topics, avatar URL, and links) as structured data."
            ),
            validation=["The public data was fetched and the key fields are reported."],
        )

    def validate(self, result: StepResult, context: FlowContext) -> Validation:
        if result.status is StepStatus.COMPLETED and not result.summary.strip():
            return Validation.failed("Report the fetched fields, or mark this step failed.")
        return Validation.passed()

    def route(self, result: StepResult, context: FlowContext) -> str | None:
        # A bad or private link is a dead end — stop instead of building a page.
        if result.status is StepStatus.FAILED:
            return Flow.END
        return None  # linear -> build


class BuildStep(Step):
    id = "build"
    title = "Build the HTML page"
    description = "Render the fetched data into one self-contained HTML file."

    def guide(self, context: FlowContext) -> StepGuidance:
        data = context.result_of("fetch")
        data_note = f"Use this fetched data:\n{data.summary}\n\n" if data else ""
        return StepGuidance(
            step_id=self.id,
            title=self.title,
            instructions=(
                f"{data_note}Generate ONE self-contained HTML file: all CSS inline "
                "in a <style> tag, no external JS/CSS/font requests (linking the "
                "GitHub avatar by its URL is fine). Include a clear title (the "
                "name), the description/bio, the key stats (stars, forks, language "
                "or public-repo/follower counts), topics as tag chips, and a "
                "prominent link back to the GitHub page. Make it responsive and "
                "readable in both light and dark. Save it to ./<slug>.html and "
                "report the path."
            ),
            inputs_required=["The fetched fields from the previous step"],
            suggested_tools=["write_file / Write"],
            output_contract="Path to a single self-contained .html file built from the data.",
            validation=["A self-contained HTML file was written and its path reported."],
        )

    def validate(self, result: StepResult, context: FlowContext) -> Validation:
        if ".html" not in result.summary.lower():
            return Validation.failed("Report the path to the .html file you wrote.")
        return Validation.passed()


class PreviewStep(Step):
    id = "preview"
    title = "Preview and verify"
    description = "Open the page and confirm it renders correctly."

    def guide(self, context: FlowContext) -> StepGuidance:
        return StepGuidance(
            step_id=self.id,
            title=self.title,
            instructions=(
                "Open the HTML file in a browser (or otherwise render it) and check "
                "it: the data is correct, the link back to GitHub works, the layout "
                "isn't broken, and it's readable in light and dark. Fix anything "
                "obviously off, then report the final file path."
            ),
            inputs_required=["The HTML file from the build step"],
            suggested_tools=["open <file> / browser", "edit / Edit"],
            output_contract="Confirmation the page renders correctly and the final file path.",
            validation=["The page was viewed and confirmed to render."],
            is_last=True,
        )

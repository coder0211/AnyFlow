"""Self-contained example: turn a public GitHub link into an HTML page.

Run it:
    python examples/github_page.py                         # default repo
    python examples/github_page.py https://github.com/psf/requests
    python examples/github_page.py https://github.com/torvalds   # a user/org

Unlike the scripted ship-hotfix demo, THIS example is a real (tiny) agent: it
starts the `github-page` flow, and at each step it actually does the work the
guidance describes — fetches the public GitHub REST API (stdlib only, no token),
writes a single self-contained HTML file, and reports back through
`complete_step`. The flow supplies the procedure and the gate; this script
supplies the tools. The result is a real `build/<slug>.html` you can open.

If the link is private or 404s, the `fetch` step reports failed and the flow
ends — you'll see the gate stop it instead of building an empty page.
"""

from __future__ import annotations

import asyncio
import json
import sys
import urllib.error
import urllib.request
from html import escape
from pathlib import Path
from urllib.parse import urlparse

from anyflow.server import mcp

API = "https://api.github.com"
DEFAULT_URL = "https://github.com/octocat/Hello-World"
OUT_DIR = Path("build")


def _unwrap(result: object) -> dict:
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        return structured.get("result", structured)
    content = getattr(result, "content", None)
    if content:
        return json.loads(content[0].text)
    raise RuntimeError(f"could not unwrap tool result: {result!r}")


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "any-flow-example"})
    with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 (trusted host)
        return json.loads(resp.read().decode())


def fetch(github_url: str) -> tuple[str, dict]:
    """Do the `fetch` step for real. Returns (kind, data); raises on 404/private."""
    parts = [p for p in urlparse(github_url).path.split("/") if p]
    if len(parts) >= 2:  # owner/repo
        return "repo", _get(f"{API}/repos/{parts[0]}/{parts[1]}")
    if len(parts) == 1:  # user or org
        return "user", _get(f"{API}/users/{parts[0]}")
    raise ValueError(f"can't parse a GitHub owner/repo or user from {github_url!r}")


def _chip(text: str) -> str:
    return f'<span class="chip">{escape(text)}</span>'


def build_html(kind: str, d: dict) -> str:
    """Do the `build` step for real: one self-contained, theme-aware HTML page."""
    if kind == "repo":
        title = d["full_name"]
        subtitle = d.get("description") or "No description provided."
        avatar = d["owner"]["avatar_url"]
        link = d["html_url"]
        stats = [
            ("★ Stars", f"{d.get('stargazers_count', 0):,}"),
            ("Forks", f"{d.get('forks_count', 0):,}"),
            ("Open issues", f"{d.get('open_issues_count', 0):,}"),
            ("Language", d.get("language") or "—"),
        ]
        chips = "".join(_chip(t) for t in d.get("topics", []))
    else:
        title = d.get("name") or d["login"]
        subtitle = d.get("bio") or f"@{d['login']}"
        avatar = d["avatar_url"]
        link = d["html_url"]
        stats = [
            ("Public repos", f"{d.get('public_repos', 0):,}"),
            ("Followers", f"{d.get('followers', 0):,}"),
            ("Following", f"{d.get('following', 0):,}"),
            ("Gists", f"{d.get('public_gists', 0):,}"),
        ]
        chips = _chip(d.get("location") or "GitHub") + (
            _chip(d["company"]) if d.get("company") else ""
        )

    stat_cards = "".join(
        f'<div class="stat"><div class="n">{escape(str(v))}</div>'
        f'<div class="k">{escape(k)}</div></div>'
        for k, v in stats
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>
  :root {{ color-scheme: light dark; --bg:#fff; --fg:#1f2328; --muted:#59636e;
    --card:#f6f8fa; --border:#d1d9e0; --accent:#0969da; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg:#0d1117; --fg:#e6edf3;
    --muted:#9198a1; --card:#161b22; --border:#30363d; --accent:#4493f8; }} }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--fg); font:16px/1.55
    -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
    display:flex; min-height:100vh; align-items:center; justify-content:center; padding:2rem; }}
  .card {{ width:100%; max-width:640px; background:var(--card);
    border:1px solid var(--border); border-radius:16px; padding:2rem; }}
  header {{ display:flex; gap:1rem; align-items:center; }}
  img.avatar {{ width:72px; height:72px; border-radius:50%; border:1px solid var(--border); }}
  h1 {{ margin:0; font-size:1.5rem; }}
  p.sub {{ margin:.25rem 0 0; color:var(--muted); }}
  .stats {{ display:grid; grid-template-columns:repeat(2,1fr); gap:.75rem; margin:1.5rem 0; }}
  @media (min-width:520px) {{ .stats {{ grid-template-columns:repeat(4,1fr); }} }}
  .stat {{ background:var(--bg); border:1px solid var(--border); border-radius:10px;
    padding:.75rem; text-align:center; }}
  .stat .n {{ font-size:1.25rem; font-weight:700; }}
  .stat .k {{ font-size:.75rem; color:var(--muted); }}
  .chips {{ display:flex; flex-wrap:wrap; gap:.4rem; margin-bottom:1.5rem; }}
  .chip {{ font-size:.8rem; padding:.15rem .6rem; border-radius:999px;
    background:var(--bg); border:1px solid var(--border); color:var(--muted); }}
  a.btn {{ display:inline-block; background:var(--accent); color:#fff;
    text-decoration:none; padding:.6rem 1.1rem; border-radius:8px; font-weight:600; }}
  footer {{ margin-top:1.5rem; font-size:.75rem; color:var(--muted); }}
</style>
</head>
<body>
  <main class="card">
    <header>
      <img class="avatar" src="{escape(avatar)}" alt="avatar">
      <div><h1>{escape(title)}</h1><p class="sub">{escape(subtitle)}</p></div>
    </header>
    <div class="stats">{stat_cards}</div>
    <div class="chips">{chips}</div>
    <a class="btn" href="{escape(link)}">View on GitHub →</a>
    <footer>Generated by any-flow · github-page flow</footer>
  </main>
</body>
</html>
"""


async def main() -> None:
    github_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL

    async def call(name: str, args: dict) -> dict:
        return _unwrap(await mcp.call_tool(name, args))

    started = await call("start_workflow", {"workflow_id": "github-page"})
    sid = started["session_id"]
    current = started["current_step"]
    print(f"▶️  github-page · {github_url}\n")

    kind: str = ""
    data: dict = {}
    out_path: Path | None = None

    while current is not None:
        step_id = current["step_id"]
        print(f"── {current['title']} ({step_id})")

        status, summary = "completed", ""
        if step_id == "fetch":
            try:
                kind, data = fetch(github_url)
                name = data.get("full_name") or data.get("login")
                summary = f"Fetched {kind} {name}."
                print(f"   ✅ {summary}")
            except (urllib.error.HTTPError, urllib.error.URLError, ValueError) as e:
                status, summary = "failed", f"Could not fetch {github_url}: {e}"
                print(f"   ⚠️  {summary}")
        elif step_id == "build":
            OUT_DIR.mkdir(exist_ok=True)
            slug = (data.get("full_name") or data.get("login")).replace("/", "-")
            out_path = OUT_DIR / f"{slug}.html"
            out_path.write_text(build_html(kind, data), encoding="utf-8")
            summary = f"Wrote self-contained page to {out_path}."
            print(f"   ✅ {summary}")
        elif step_id == "preview":
            summary = f"Open {out_path} in a browser to view it."
            print(f"   ✅ {summary}")

        advanced = await call(
            "complete_step",
            {"session_id": sid, "step_id": step_id, "status": status, "summary": summary},
        )
        current = advanced["next_step"]
        if advanced["flow_complete"]:
            break

    if out_path and out_path.exists():
        print(f"\n🎉 done → {out_path}  (open it in your browser)")
    else:
        print("\n🛑 flow stopped at the fetch gate — no page built.")


if __name__ == "__main__":
    asyncio.run(main())

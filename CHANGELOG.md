# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to
adhere to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **`github-page` flow**: the easiest built-in to try — hand it a public GitHub
  URL and it goes fetch (public REST API) → build (one self-contained HTML page)
  → preview, with a gate that stops on a bad/private link. Runnable, real-fetch
  demo: `python examples/github_page.py <github-url>`.
- **Live progress**: every step response now carries a `progress` map (current
  step index, percent done, the ordered `path` taken with loops, completed and
  remaining steps, and per-step attempt counts). New `get_progress(session_id)`
  MCP tool returns it on demand without advancing the flow.
- **Loop guard**: `Step.max_attempts` caps how many times a step may be entered.
  When a branch would re-enter a step past its ceiling, the engine refuses to
  advance and tells the agent to escalate — so a failing gate can't ping-pong
  forever. The built-in `ship-hotfix` runbook caps its `patch` retry loop at 3.
- **Session listing / resume**: `SessionStore.list_sessions()` plus a
  `list_sessions(status=…)` MCP tool enumerate stored sessions, so an interrupted
  run can be found by `session_id` and picked back up (with a persistent store).

## [0.1.0]

Initial public release.

### Added

- **Core interfaces** (`anyflow.core`): `Flow` and `Step` for defining workflows,
  `FlowContext` for per-session state, and a `FlowRegistry`.
- **Stateful sessions**: `SessionManager` with a swappable `SessionStore`
  (`InMemorySessionStore` by default).
- **SQLite persistence**: `anyflow.stores.SqliteSessionStore` for long-running or
  multi-process servers, selected via the `ANYFLOW_DB` environment variable.
- **MCP server** (`anyflow.server`): the `list_workflows`, `get_workflow_plan`,
  `start_workflow`, `get_current_step`, `complete_step`, and `abort_workflow`
  tools over stdio.
- **Built-in example flows**: `ship-hotfix` (a multi-tool release runbook with
  two branch gates), `fix-bug` (a branching retry loop), and `refactor-python`
  (a linear flow).
- Test suite covering the engine, both branching flows, SQLite durability, and an
  end-to-end agent-loop eval.

[Unreleased]: https://github.com/coder0211/any-flow/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/coder0211/any-flow/releases/tag/v0.1.0

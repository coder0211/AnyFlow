# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to
adhere to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

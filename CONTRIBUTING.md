# Contributing to any-flow

Thanks for helping build the flow library. The most valuable contribution is a
new, well-scoped **flow** — a procedure other people's agents can reuse.

## Setup

```bash
python -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
pytest && ruff check .
```

## The one rule of any-flow

**Flows guide; they do not execute.** A step returns *instructions* for the
agent — what to do, which tools to reach for, how to know it's done. It must not
try to do the agent's work itself (no file edits, no shell calls, no LLM calls
inside a step). If a step wants to "run the tests", it says so in
`instructions`; the agent runs them.

This keeps flows pure functions of their context, which makes them trivial to
test and safe to run in any agent.

## Adding a flow

1. Copy an existing flow directory under `anyflow/flows/` as a template:
   - `refactor/` — a simple **linear** flow.
   - `bugfix/` — a **branching** flow (a failed `verify` step routes back
     to `locate` via `Step.route`).
2. Implement your `Step` subclasses in `steps.py`. Each needs `id`, `title`, and
   a `guide(context)` returning a `StepGuidance`. Add `validate()` to enforce an
   output contract, and `route()` to branch.
3. Declare the `Flow` in `flow.py`: `id`, `name`, `goal`, `when_to_use`, and the
   ordered `steps` list. Fill in `prerequisites` and `success_criteria` — agents
   rely on them to pick and finish the flow.
4. Register it with **one line** in `anyflow/flows/__init__.py`.
5. Add tests under `tests/` (see `test_bugfix_flow.py` for the pattern: run the
   session to completion, assert branching, assert validation rejects bad input).

## Design guidelines

- **Small steps, verifiable output.** Each step should have an `output_contract`
  an agent can satisfy and you can check in `validate()`.
- **Progressive disclosure.** Keep `description` (shown in the plan) short; put
  detail in `guide()`, which is only fetched when the step is reached.
- **Deterministic guidance.** `guide()` may read `context` but should not depend
  on wall-clock time, randomness, or network — same context, same guidance.

## Before opening a PR

- `ruff check .` is clean.
- `pytest` passes.
- New flow has tests and appears in `list_workflows()`.

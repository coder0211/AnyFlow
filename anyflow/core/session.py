"""Stateful session tracking — the "where am I in the flow" bookkeeping.

The MCP server is stateful by design: starting a workflow returns a session id,
and the agent drives it forward with `complete_step`. `SessionManager` persists
through a `SessionStore` (see `anyflow.core.store`); which concrete store it uses
is decided by the caller, so the engine stays storage-agnostic.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .context import FlowContext
from .flow import Flow
from .models import (
    FlowProgress,
    JsonValue,
    SessionStatus,
    SessionSummary,
    StepResult,
    StepStatus,
)
from .registry import FlowRegistry

if TYPE_CHECKING:
    from .store import SessionStore


@dataclass(slots=True)
class Session:
    """Live progress of one agent working through one flow."""

    id: str
    flow_id: str
    current_step_id: str | None
    status: SessionStatus = SessionStatus.RUNNING
    history: dict[str, StepResult] = field(default_factory=dict)
    variables: dict[str, JsonValue] = field(default_factory=dict)
    #: Ordered trail of every step the session has entered, repeats included, so
    #: a gate that routes back shows up as a real loop (e.g. patch, ..., patch).
    path: list[str] = field(default_factory=list)
    #: How many times each step has been entered. Feeds the per-step loop guard.
    attempts: dict[str, int] = field(default_factory=dict)

    def context(self) -> FlowContext:
        return FlowContext(
            flow_id=self.flow_id,
            session_id=self.id,
            history=self.history,
            variables=self.variables,
        )


class SessionManager:
    """Creates sessions and advances them through a flow's steps.

    Storage is injected: pass any `SessionStore` (see `anyflow.stores`).
    """

    def __init__(self, registry: FlowRegistry, store: SessionStore) -> None:
        self._registry = registry
        self._store = store

    def start(self, flow_id: str) -> tuple[Session, Flow]:
        flow = self._registry.get(flow_id)
        first = flow.first_step_id()
        session = Session(
            id=uuid.uuid4().hex,
            flow_id=flow_id,
            current_step_id=first,
        )
        _enter(session, first)
        self._store.save(session)
        return session, flow

    def get(self, session_id: str) -> Session:
        return self._store.load(session_id)

    def flow_of(self, session: Session) -> Flow:
        return self._registry.get(session.flow_id)

    def complete_step(self, session_id: str, result: StepResult) -> Session:
        """Record a step result and advance to the next step.

        Raises ValueError if the session is finished, the result targets the
        wrong step, or the step's own validation rejects the result.
        """
        session = self.get(session_id)
        if session.status is not SessionStatus.RUNNING:
            raise ValueError(f"session {session_id!r} is {session.status.value}")

        flow = self.flow_of(session)
        expected = session.current_step_id
        if expected is None:
            raise ValueError("session has no current step")
        if result.step_id != expected:
            raise ValueError(
                f"result targets {result.step_id!r} but current step is {expected!r}"
            )

        step = flow.get_step(expected)
        context = session.context()
        validation = step.validate(result, context)
        if not validation.ok:
            raise ValueError("; ".join(validation.issues) or "step validation failed")

        session.history[expected] = result
        # Recompute context so routing sees the just-recorded result.
        nxt = flow.next_step_id(expected, result, session.context())
        if nxt is not None:
            # Loop guard: refuse to re-enter a step past its ceiling rather than
            # ping-ponging a gate forever. The failed result is already recorded;
            # the session stays parked on the current step so the agent can
            # escalate or abort with full history intact.
            target = flow.get_step(nxt)
            limit = target.max_attempts
            if limit is not None and session.attempts.get(nxt, 0) >= limit:
                if target.on_exhausted is None:
                    self._store.save(session)
                    raise ValueError(
                        f"step {nxt!r} hit its retry limit ({limit}); "
                        "the flow is looping. Escalate to a human or abort_workflow."
                    )
                # Graceful hand-off: route to the declared escalation step instead.
                nxt = target.on_exhausted
                flow.get_step(nxt)  # fail fast if the escalation target is a typo
            _enter(session, nxt)
        session.current_step_id = nxt
        if nxt is None:
            session.status = SessionStatus.COMPLETED
        self._store.save(session)
        return session

    def abort(self, session_id: str) -> Session:
        session = self.get(session_id)
        session.status = SessionStatus.ABORTED
        session.current_step_id = None
        self._store.save(session)
        return session

    def progress(self, session: Session) -> FlowProgress:
        """Build a live map of where `session` sits in its flow."""
        flow = self.flow_of(session)
        order = flow.step_ids()
        completed = [
            sid for sid in order
            if (r := session.history.get(sid)) and r.status is StepStatus.COMPLETED
        ]
        remaining = [
            sid for sid in order
            if sid != session.current_step_id and sid not in session.history
        ]
        current = session.current_step_id
        index = order.index(current) + 1 if current in order else 0
        total = len(order)
        return FlowProgress(
            flow_id=session.flow_id,
            session_id=session.id,
            status=session.status.value,
            current_step_id=current,
            current_index=index,
            total_steps=total,
            percent=round(len(completed) / total * 100) if total else 0,
            completed_steps=completed,
            remaining_steps=remaining,
            path=list(session.path),
            attempts=dict(session.attempts),
        )

    def list_sessions(self, status: SessionStatus | None = None) -> list[SessionSummary]:
        """Summaries of stored sessions, newest first, optionally filtered."""
        summaries = [
            SessionSummary(
                session_id=s.id,
                flow_id=s.flow_id,
                status=s.status.value,
                current_step_id=s.current_step_id,
                steps_completed=sum(
                    1 for r in s.history.values() if r.status is StepStatus.COMPLETED
                ),
            )
            for s in self._store.list_sessions()
            if status is None or s.status is status
        ]
        return summaries


def _enter(session: Session, step_id: str) -> None:
    """Record a step entry: extend the visit trail and bump its attempt count."""
    session.path.append(step_id)
    session.attempts[step_id] = session.attempts.get(step_id, 0) + 1

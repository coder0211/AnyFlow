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
from .models import SessionStatus, StepResult
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
    variables: dict[str, str] = field(default_factory=dict)

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
        session = Session(
            id=uuid.uuid4().hex,
            flow_id=flow_id,
            current_step_id=flow.first_step_id(),
        )
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

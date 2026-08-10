"""Registry that holds the known flows the MCP server can serve.

Flows register themselves explicitly (import-and-register) rather than by magic
scanning: it keeps the dependency graph obvious and startup fast. A contributor
adds a flow by appending one line to `anyflow.flows.load_builtin_flows`.
"""

from __future__ import annotations

from .flow import Flow


class FlowRegistry:
    """An in-memory catalog of Flow instances keyed by flow id."""

    def __init__(self) -> None:
        self._flows: dict[str, Flow] = {}

    def register(self, flow: Flow) -> None:
        if flow.id in self._flows:
            raise ValueError(f"flow id {flow.id!r} already registered")
        self._flows[flow.id] = flow

    def get(self, flow_id: str) -> Flow:
        try:
            return self._flows[flow_id]
        except KeyError:
            known = ", ".join(sorted(self._flows)) or "(none)"
            raise KeyError(f"unknown flow {flow_id!r}; registered: {known}") from None

    def all(self) -> list[Flow]:
        return list(self._flows.values())

    def __contains__(self, flow_id: object) -> bool:
        return flow_id in self._flows

    def __len__(self) -> int:
        return len(self._flows)

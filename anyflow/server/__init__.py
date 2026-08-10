"""The MCP server layer — wires the flow registry into an MCPServer.

`from anyflow.server import mcp` gives the configured server; `main()` runs it
over stdio (also reachable as `python -m anyflow.server`).
"""

from .app import main, mcp

__all__ = ["main", "mcp"]

"""MCP client — async wrapper around FastMCP's SSE client.

Provides a single ``MCPClient`` class that maintains one persistent SSE
connection per MCP server and exposes an async ``call_tool`` method.

The client is designed to be used as an async context manager so that
connections are cleaned up properly::

    async with MCPClient() as client:
        result = await client.call_tool("metrics", "get_sales_summary",
                                        {"start_date": "2026-03-01"})

Or use the module-level ``get_mcp_client()`` singleton for long-lived usage
inside a FastAPI lifespan.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastmcp import Client
from fastmcp.client.transports import SSETransport

from backend.core.config import settings


# ── Server URL map ────────────────────────────────────────────────────────────


def _server_urls() -> dict[str, str]:
    return {
        "metrics": (
            f"http://{settings.mcp_metrics_host}:{settings.mcp_metrics_port}/sse"
        ),
        "inventory": (
            f"http://{settings.mcp_inventory_host}:{settings.mcp_inventory_port}/sse"
        ),
        "marketing": (
            f"http://{settings.mcp_marketing_host}:{settings.mcp_marketing_port}/sse"
        ),
        "support": (
            f"http://{settings.mcp_support_host}:{settings.mcp_support_port}/sse"
        ),
    }


# ── Client ────────────────────────────────────────────────────────────────────


class MCPClient:
    """Async wrapper that routes tool calls to the correct MCP server.

    Each ``call_tool`` opens a fresh SSE connection, calls the tool, and
    closes the connection.  This is the safest approach given that FastMCP
    SSE connections are not thread-safe for concurrent calls.
    """

    def __init__(self) -> None:
        self._urls = _server_urls()

    async def call_tool(
        self,
        server: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        """Call a named tool on one of the MCP servers.

        Args:
            server: One of 'metrics', 'inventory', 'marketing', 'support'.
            tool_name: The MCP tool name (e.g. 'get_sales_summary').
            arguments: Dict of tool arguments.

        Returns:
            The tool's return value (already deserialised from JSON).

        Raises:
            ValueError: If *server* is not a known server name.
            Exception: Any error raised by the MCP server tool.
        """
        if server not in self._urls:
            raise ValueError(
                f"Unknown MCP server '{server}'. Choose from: {sorted(self._urls)}"
            )

        url = self._urls[server]
        async with Client(SSETransport(url)) as client:
            result = await client.call_tool(tool_name, arguments or {})

        # Newer FastMCP versions return a CallToolResult object with a
        # .content attribute; older versions return a plain list of content
        # blocks directly.  Normalise both shapes here.
        import json

        content_blocks: list[Any] = []
        if isinstance(result, list):
            content_blocks = result
        elif hasattr(result, "content") and isinstance(result.content, list):
            content_blocks = result.content

        if content_blocks:
            texts = [b.text for b in content_blocks if hasattr(b, "text")]
            if len(texts) == 1:
                try:
                    return json.loads(texts[0])
                except (json.JSONDecodeError, TypeError):
                    return texts[0]
            return texts

        return result

    async def call_tools_parallel(
        self,
        calls: list[tuple[str, str, dict[str, Any]]],
    ) -> list[Any]:
        """Call multiple tools in parallel.

        Args:
            calls: List of (server, tool_name, arguments) tuples.

        Returns:
            List of results in the same order as *calls*.
        """
        tasks = [self.call_tool(server, tool, args) for server, tool, args in calls]
        return await asyncio.gather(*tasks, return_exceptions=True)


# ── Module-level singleton ────────────────────────────────────────────────────

_client: MCPClient | None = None


def get_mcp_client() -> MCPClient:
    """Return the module-level MCPClient singleton."""
    global _client
    if _client is None:
        _client = MCPClient()
    return _client

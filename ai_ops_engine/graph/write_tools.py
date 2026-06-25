"""Registry of write (state-mutating) MCP tools and their target servers.

Adding a new write tool means editing only this file.
"""

from __future__ import annotations

WRITE_TOOL_SERVER: dict[str, str] = {
    "restock_product": "inventory",
    "pause_campaign": "marketing",
    "apply_discount": "marketing",
    "create_support_ticket": "support",
}

WRITE_TOOL_NAMES: frozenset[str] = frozenset(WRITE_TOOL_SERVER)

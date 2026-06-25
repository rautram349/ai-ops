"""Inventory domain agent."""

from __future__ import annotations

from ai_ops_engine.agents.base import run_domain_agent
from ai_ops_engine.agents.category_utils import _extract_category
from ai_ops_engine.graph.state import AgentState
from ai_ops_engine.prompts import INVENTORY_SYSTEM as _INVENTORY_SYSTEM

# get_near_stockout does NOT accept a category param
_CATEGORY_TOOLS = {"get_stock_levels"}


def _sanitize_inventory_tools(tool_calls: list[dict], query: str) -> list[dict]:
    """Inject category into get_stock_levels when the query names a product category."""
    category = _extract_category(query)
    if not category:
        return tool_calls
    sanitized = []
    for tc in tool_calls:
        if tc.get("tool") in _CATEGORY_TOOLS:
            args = dict(tc.get("arguments", {}))
            args["category"] = category  # always override
            sanitized.append({**tc, "arguments": args})
        else:
            sanitized.append(tc)
    return sanitized


def _defaults() -> list[dict]:
    return [
        {"server": "inventory", "tool": "get_stock_levels", "arguments": {}},
        {"server": "inventory", "tool": "get_near_stockout", "arguments": {}},
    ]


async def inventory_agent(state: AgentState) -> dict:
    """Investigate inventory domain."""
    return await run_domain_agent(
        state=state,
        domain="inventory",
        server="inventory",
        system_prompt=_INVENTORY_SYSTEM,
        default_tools=_defaults(),
        node_name="inventory_agent",
        tool_sanitizer=_sanitize_inventory_tools,
    )

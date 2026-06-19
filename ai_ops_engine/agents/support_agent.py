"""Support domain agent."""

from __future__ import annotations

from ai_ops_engine.agents.base import _days_ago, _today, run_domain_agent
from ai_ops_engine.graph.state import AgentState
from ai_ops_engine.prompts import SUPPORT_SYSTEM as _SUPPORT_SYSTEM

# Keyword aliases → canonical DB category name (ILIKE handles remaining case)
_CATEGORY_ALIASES: dict[str, str] = {
    "electronics": "Electronics",
    "clothing": "Clothing",
    "apparel": "Clothing",
    "fashion": "Clothing",
    "home": "Home & Kitchen",
    "kitchen": "Home & Kitchen",
    "beauty": "Beauty & Personal Care",
    "personal care": "Beauty & Personal Care",
    "skincare": "Beauty & Personal Care",
    "sports": "Sports & Outdoors",
    "outdoors": "Sports & Outdoors",
    "outdoor": "Sports & Outdoors",
    "fitness": "Sports & Outdoors",
    "books": "Books & Media",
    "media": "Books & Media",
}

_CATEGORY_TOOLS = {"get_review_sentiment", "get_complaint_summary"}


def _extract_category(query: str) -> str | None:
    """Return the canonical DB category for the first matching keyword in query."""
    q_lower = query.lower()
    for keyword, category in _CATEGORY_ALIASES.items():
        if keyword in q_lower:
            return category
    return None


def _sanitize_support_tools(tool_calls: list[dict], query: str) -> list[dict]:
    """Inject category into sentiment/complaint tools when the query names one."""
    category = _extract_category(query)
    if not category:
        return tool_calls

    sanitized = []
    for tc in tool_calls:
        if tc.get("tool") in _CATEGORY_TOOLS:
            args = dict(tc.get("arguments", {}))
            args["category"] = category  # always override — LLM may emit null
            sanitized.append({**tc, "arguments": args})
        else:
            sanitized.append(tc)
    return sanitized


def _defaults() -> list[dict]:
    return [
        {"server": "support", "tool": "get_complaint_summary",
         "arguments": {"start_date": _days_ago(30), "end_date": _today()}},
        {"server": "support", "tool": "get_review_sentiment",
         "arguments": {"start_date": _days_ago(30), "end_date": _today()}},
    ]


async def support_agent(state: AgentState) -> dict:
    """Investigate support domain."""
    return await run_domain_agent(
        state=state,
        domain="support",
        server="support",
        system_prompt=_SUPPORT_SYSTEM,
        default_tools=_defaults(),
        node_name="support_agent",
        tool_sanitizer=_sanitize_support_tools,
    )

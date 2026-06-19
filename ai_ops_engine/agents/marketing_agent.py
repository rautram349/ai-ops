"""Marketing domain agent."""

from __future__ import annotations

from ai_ops_engine.agents.base import _days_ago, _today, run_domain_agent
from ai_ops_engine.graph.state import AgentState
from ai_ops_engine.prompts import MARKETING_SYSTEM as _MARKETING_SYSTEM


def _defaults() -> list[dict]:
    return [
        {"server": "marketing", "tool": "get_campaign_status",
         "arguments": {"start_date": _days_ago(30), "end_date": _today()}},
        {"server": "marketing", "tool": "get_channel_performance",
         "arguments": {"start_date": _days_ago(30), "end_date": _today()}},
    ]


async def marketing_agent(state: AgentState) -> dict:
    """Investigate marketing domain."""
    return await run_domain_agent(
        state=state,
        domain="marketing",
        server="marketing",
        system_prompt=_MARKETING_SYSTEM,
        default_tools=_defaults(),
        node_name="marketing_agent",
    )

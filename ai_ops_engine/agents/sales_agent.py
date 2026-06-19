"""Sales / Metrics domain agent."""

from __future__ import annotations

from ai_ops_engine.agents.base import _days_ago, _today, run_domain_agent
from ai_ops_engine.graph.state import AgentState
from ai_ops_engine.prompts import SALES_SYSTEM as _SALES_SYSTEM


def _defaults() -> list[dict]:
    return [
        {"server": "metrics", "tool": "get_sales_summary",
         "arguments": {"start_date": _days_ago(30), "end_date": _today()}},
    ]


async def sales_agent(state: AgentState) -> dict:
    """Investigate sales/metrics domain."""
    return await run_domain_agent(
        state=state,
        domain="sales",
        server="metrics",
        system_prompt=_SALES_SYSTEM,
        default_tools=_defaults(),
        node_name="sales_agent",
    )

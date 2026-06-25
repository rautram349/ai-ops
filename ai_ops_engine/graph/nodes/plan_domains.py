"""Graph node — plan_domains: decide which agents to activate."""

from __future__ import annotations

import json

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ai_ops_engine.graph.domains import DOMAINS
from ai_ops_engine.graph.nodes.shared import _strip_code_fences
from ai_ops_engine.graph.state import AgentState
from ai_ops_engine.llm import get_llm
from ai_ops_engine.prompts import PLAN_DOMAINS_SYSTEM as _PLAN_DOMAINS_SYSTEM

logger = structlog.get_logger(__name__)


def _default_domains(intent: str) -> list[str]:
    """Fallback domain list when LLM parsing fails."""
    mapping: dict[str, list[str]] = {
        "sales_analysis": ["sales", "inventory", "marketing"],
        "inventory_check": ["inventory"],
        "marketing_performance": ["marketing"],
        "support_analysis": ["support"],
        "multi_domain": ["sales", "inventory", "marketing"],
    }
    return mapping.get(intent, ["sales"])


async def plan_domains(state: AgentState) -> dict:
    """Decide which domains to investigate based on intent and query."""

    llm = get_llm()
    query = state["user_query"]
    intent = state["intent"]

    response = await llm.ainvoke(
        [
            SystemMessage(content=_PLAN_DOMAINS_SYSTEM),
            HumanMessage(content=f"Intent: {intent}\nQuery: {query}"),
        ]
    )


    raw: str = str(response.content) if hasattr(response, "content") else str(response)
    logger.info("plan_domains_raw", raw=raw[:300], intent=intent)

    try:
        cleaned = _strip_code_fences(raw)
        parsed = json.loads(cleaned)
        domains: list[str] = parsed.get("domains", [])
    except (json.JSONDecodeError, AttributeError):
        domains = _default_domains(intent)

    valid = DOMAINS
    domains = [d for d in domains if d in valid]
    if not domains:
        domains = _default_domains(intent)

    logger.info("plan_domains", domains=domains, intent=intent)

    return {
        "domain_plan": domains,
        "messages": [
            AIMessage(content=f"[plan_domains] Investigating: {', '.join(domains)}")
        ],
    }

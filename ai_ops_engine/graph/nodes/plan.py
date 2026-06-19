"""Graph node — plan: decide if write actions are needed and queue approvals."""

from __future__ import annotations

import json

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ai_ops_engine.graph.nodes.shared import _now, _strip_code_fences, _summarise_tool_results
from ai_ops_engine.graph.state import AgentState, PendingApproval
from ai_ops_engine.llm import get_llm
from ai_ops_engine.prompts import PLAN_SYSTEM as _PLAN_SYSTEM

logger = structlog.get_logger(__name__)


async def plan(state: AgentState) -> dict:
    """Decide if write actions are needed and queue approval requests."""
    
    llm = get_llm()

    tool_summary = _summarise_tool_results(state["tool_results"])

    response = await llm.ainvoke([
        SystemMessage(content=_PLAN_SYSTEM),
        HumanMessage(content=(
            f"User query: \"{state['user_query']}\"\n\n"
            f"IMPORTANT: If the query contains imperative verbs like 'restock', 'fix it', "
            f"'pause', 'apply', 'create', 'go ahead', or similar action commands, "
            f"it IS an explicit action request → set needs_write=true and populate actions.\n\n"
            f"Data gathered:\n{tool_summary}"
        )),
    ])
    

    try:
        cleaned = _strip_code_fences(response.content if hasattr(response, "content") else str(response))
        parsed = json.loads(cleaned)
    except (json.JSONDecodeError, AttributeError):
        parsed = {"needs_write": False, "actions": []}

    needs_write: bool = bool(parsed.get("needs_write", False))
    actions: list[dict] = parsed.get("actions", []) if needs_write else []

    pending: list[PendingApproval] = [
        PendingApproval(
            tool=a["tool"],
            server=a["server"],
            arguments=a.get("arguments", {}),
            reason=a.get("reason", ""),
            risk_level=a.get("risk_level", "medium"),
            reversible=bool(a.get("reversible", True)),
        )
        for a in actions
    ]

    logger.info("plan", needs_write=needs_write, num_actions=len(pending))

    summary = f"Write actions needed: {needs_write}. Pending approvals: {len(pending)}."
    return {
        "needs_write": needs_write,
        "pending_approvals": pending,
        "approved": not needs_write,
        "messages": [AIMessage(content=f"[plan] {summary}")],
    }

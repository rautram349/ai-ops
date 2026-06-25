"""Graph node — plan: decide if write actions are needed and queue approvals."""

from __future__ import annotations

import json

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ai_ops_engine.graph.nodes.plan_restock import (
    _build_restock_approvals,
    _extract_quantity,
    _extract_region,
    _is_restock_request,
    _missing_restock_args_blocker,
    _resolve_restock_product_ids,
)
from ai_ops_engine.graph.nodes.shared import _strip_code_fences, _summarise_tool_results
from ai_ops_engine.graph.state import AgentState, PendingApproval
from ai_ops_engine.llm import get_llm
from ai_ops_engine.prompts import PLAN_SYSTEM as _PLAN_SYSTEM

logger = structlog.get_logger(__name__)

async def plan(state: AgentState) -> dict:
    """Decide if write actions are needed and queue approval requests."""
    query = state["user_query"]

    if _is_restock_request(query):
        product_ids, blocker = await _resolve_restock_product_ids(query)
        if blocker:
            return {
                "needs_write": False,
                "pending_approvals": [],
                "approved": True,
                "action_plan_blocker": blocker,
                "messages": [AIMessage(content=f"[plan] {blocker['summary']}")],
            }
        region = _extract_region(query)
        quantity = _extract_quantity(query)
        blocker = _missing_restock_args_blocker(
            product_ids=product_ids,
            region=region,
            quantity=quantity,
        )
        if blocker:
            return {
                "needs_write": False,
                "pending_approvals": [],
                "approved": True,
                "action_plan_blocker": blocker,
                "messages": [AIMessage(content=f"[plan] {blocker['summary']}")],
            }

        assert region is not None
        assert quantity is not None
        pending = _build_restock_approvals(
            product_ids,
            region=region,
            quantity=quantity,
        )
        summary = f"Write actions needed: True. Pending approvals: {len(pending)}."
        logger.info(
            "plan_deterministic_restock",
            num_products=len(product_ids),
            num_actions=len(pending),
        )
        return {
            "needs_write": True,
            "pending_approvals": pending,
            "approved": False,
            "action_plan_blocker": None,
            "messages": [AIMessage(content=f"[plan] {summary}")],
        }

    llm = get_llm()

    tool_summary = _summarise_tool_results(state["tool_results"])

    response = await llm.ainvoke([
        SystemMessage(content=_PLAN_SYSTEM),
        HumanMessage(content=(
            f"User query: \"{query}\"\n\n"
            f"IMPORTANT: If the query contains imperative verbs like 'restock', 'fix it', "
            f"'pause', 'apply', 'create', 'go ahead', or similar action commands, "
            f"it IS an explicit action request → set needs_write=true and populate actions.\n\n"
            f"Data gathered:\n{tool_summary}"
        )),
    ])


    try:
        cleaned = _strip_code_fences(str(response.content) if hasattr(response, "content") else str(response))
        parsed = json.loads(cleaned)
    except (json.JSONDecodeError, AttributeError):
        parsed = {"needs_write": False, "actions": []}

    needs_write: bool = bool(parsed.get("needs_write", False))
    actions: list[dict] = parsed.get("actions", []) if needs_write else []

    pending = [
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
        "action_plan_blocker": None,
        "messages": [AIMessage(content=f"[plan] {summary}")],
    }

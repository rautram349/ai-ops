"""Synthetic graph nodes — deterministic response paths that bypass the main LLM respond node."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ai_ops_engine.graph.nodes.shared import SKIP_MESSAGE_PREFIXES
from ai_ops_engine.graph.state import AgentState, PendingApproval
from ai_ops_engine.llm import get_llm
from ai_ops_engine.prompts import UNKNOWN_SYSTEM as _UNKNOWN_SYSTEM


def _respond_guardrail(state: AgentState) -> dict:
    """Deterministic refusal for prompts outside the AI-ops scope."""
    category = state.get("guardrail_category", "irrelevant")
    summary = (
        "I can't help with that request because it's outside the AI-ops operational scope. "
        "I can help investigate sales, inventory, marketing, support, incidents, and approval workflows."
    )
    if category == "prompt_injection":
        summary = (
            "I can't help with requests to override instructions, reveal hidden prompts, or access secrets. "
            "Ask me about sales, inventory, marketing, support, incidents, or operational actions instead."
        )

    return {
        "response_summary": summary,
        "response_details": {
            "summary": summary,
            "findings": [
                {
                    "title": "Prompt blocked by scope guardrail",
                    "detail": state.get("guardrail_reason", "The prompt is outside the supported AI-ops domain."),
                    "severity": "info",
                }
            ],
            "recommendations": [
                {
                    "action_type": "ask_operational_question",
                    "reason": "Try asking about revenue anomalies, stockouts, campaign performance, support complaints, incidents, or approvals.",
                    "risk_level": "low",
                    "reversible": True,
                }
            ],
            "actions_taken": [],
            "pending_approvals": [],
        },
        "messages": [AIMessage(content=summary)],
    }


async def _respond_unknown(state: AgentState) -> dict:
    """Use LLM to generate a smart, context-aware conversational reply."""
    llm = get_llm()
    query = state["user_query"]

    prior_msgs = [
        m
        for m in state.get("messages", [])
        if isinstance(m, (HumanMessage, AIMessage))
        and not str(m.content).startswith(SKIP_MESSAGE_PREFIXES)
        and m.content != query
    ]

    llm_messages = [SystemMessage(content=_UNKNOWN_SYSTEM), *prior_msgs[-6:], HumanMessage(content=query)]

    response = await llm.ainvoke(llm_messages)
    reply: str = str(response.content) if hasattr(response, "content") else str(response)

    return {
        "response_summary": reply,
        "response_details": {
            "summary": reply,
            "findings": [],
            "recommendations": [],
            "actions_taken": [],
            "pending_approvals": [],
        },
        "messages": [AIMessage(content=reply)],
    }


def _money(value: Any) -> str:
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


def _pending_finding_from_tool(tool: str, result: dict) -> dict:
    """Convert raw tool output into a concise, human-readable finding."""
    if tool == "get_near_stockout":
        snap = result.get("snapshot_date", "the latest snapshot")
        threshold = result.get("threshold_days", "configured")
        total = int(result.get("total_at_risk") or 0)
        products = result.get("near_stockout_products") or []
        if total <= 0:
            detail = (
                f"No products are currently below the {threshold}-day stock "
                f"threshold as of {snap}."
            )
            affected_products: list[str] = []
            affected_regions: list[str] = []
        else:
            sample = products[:3]
            items = ", ".join(
                f"{p.get('product_id')} in {p.get('region')} "
                f"({p.get('closing_stock')} units, {p.get('days_of_stock_remaining')} days left)"
                for p in sample
            )
            detail = (
                f"{total} product-region combination(s) are below the "
                f"{threshold}-day stock threshold as of {snap}. Top risks: {items}."
            )
            affected_products = [
                p.get("product_id") for p in sample if p.get("product_id")
            ]
            affected_regions = [p.get("region") for p in sample if p.get("region")]
        return {
            "title": "Near-stockout status",
            "detail": detail,
            "severity": "warning" if total > 0 else "info",
            "root_cause": "",
            "affected_products": affected_products,
            "affected_regions": affected_regions,
        }

    if tool == "get_stockout_events":
        period = result.get("period") or {}
        events = result.get("stockout_events") or []
        total_lost = result.get("total_lost_revenue_estimate") or 0
        if not events:
            detail = (
                f"No stockout events were found for "
                f"{period.get('start', 'the selected period')} to "
                f"{period.get('end', 'the selected period')}."
            )
            affected_products = []
            affected_regions = []
        else:
            sample = events[:3]
            items = ", ".join(
                f"{e.get('product_id')} in {e.get('region')} on {e.get('date')}"
                for e in sample
            )
            detail = (
                f"{len(events)} stockout event(s) were found from "
                f"{period.get('start')} to {period.get('end')}, with estimated "
                f"lost revenue of {_money(total_lost)}. Examples: {items}."
            )
            affected_products = [
                e.get("product_id") for e in sample if e.get("product_id")
            ]
            affected_regions = [e.get("region") for e in sample if e.get("region")]
        return {
            "title": "Recent stockout events",
            "detail": detail,
            "severity": "warning" if events else "info",
            "root_cause": "",
            "affected_products": affected_products,
            "affected_regions": affected_regions,
        }

    if tool == "get_stock_levels":
        snap = result.get("snapshot_date", "the latest snapshot")
        levels = result.get("stock_levels") or []
        total = result.get("total_products", len(levels))
        if not levels:
            detail = f"No stock-level rows were returned for {snap}."
            affected_products = []
            affected_regions = []
        else:
            lowest = levels[0]
            detail = (
                f"{total} stock-level row(s) were returned for {snap}. The lowest "
                f"visible stock is {lowest.get('product_id')} in "
                f"{lowest.get('region')} with {lowest.get('closing_stock')} units."
            )
            affected_products = [lowest.get("product_id")] if lowest.get("product_id") else []
            affected_regions = [lowest.get("region")] if lowest.get("region") else []
        return {
            "title": "Current stock snapshot",
            "detail": detail,
            "severity": "info",
            "root_cause": "",
            "affected_products": affected_products,
            "affected_regions": affected_regions,
        }

    return {
        "title": f"Data gathered from {tool}",
        "detail": f"{tool} returned data successfully. Raw tool output is retained internally.",
        "severity": "info",
        "root_cause": "",
        "affected_products": [],
        "affected_regions": [],
    }


def _summarize_pending_approvals(approvals: list[PendingApproval]) -> str:
    if not approvals:
        return "No approvals are currently pending."
    counts: dict[str, int] = {}
    for approval in approvals:
        tool = approval.get("tool", "action")
        counts[tool] = counts.get(tool, 0) + 1
    parts = [
        f"{count} {tool.replace('_', ' ')} approval{'s' if count != 1 else ''}"
        for tool, count in sorted(counts.items())
    ]
    return (
        f"{', '.join(parts)} waiting for review. "
        "No write operation has run yet."
    )


def _respond_pending(state: AgentState) -> dict:
    """Synthetic node: inform the user that approvals are pending."""
    approvals = state.get("pending_approvals", [])
    summary = _summarize_pending_approvals(approvals)
    existing_findings: list = []
    for tr in state.get("tool_results", []):
        if not tr.get("error") and isinstance(tr.get("result"), dict):
            existing_findings.append(_pending_finding_from_tool(tr["tool"], tr["result"]))
    if not existing_findings and approvals:
        tools = ", ".join(sorted({a.get("tool", "action") for a in approvals}))
        existing_findings.append(
            {
                "title": "Approval required before execution",
                "detail": (
                    f"{len(approvals)} pending approval request(s) were prepared "
                    f"for: {tools}. No write tool has been executed yet."
                ),
                "severity": "info",
                "root_cause": "",
                "affected_products": [
                    a.get("arguments", {}).get("product_id")
                    for a in approvals
                    if a.get("arguments", {}).get("product_id")
                ],
                "affected_regions": [
                    a.get("arguments", {}).get("region")
                    for a in approvals
                    if a.get("arguments", {}).get("region")
                ],
            }
        )
    return {
        "response_summary": summary,
        "response_details": {
            "summary": summary,
            "findings": existing_findings,
            "recommendations": [],
            "actions_taken": [],
            "pending_approvals": [dict(a) for a in approvals],
        },
    }


def _respond_action_blocked(state: AgentState) -> dict:
    """Deterministic response for action requests missing executable targets."""
    blocker = state.get("action_plan_blocker") or {}
    summary = blocker.get(
        "summary",
        "No approval was created because the action request is missing required details.",
    )
    detail = blocker.get("detail", summary)
    recommendation = blocker.get(
        "recommendation",
        "Provide a specific product ID or recognized product name to create a restock approval.",
    )
    return {
        "response_summary": summary,
        "response_details": {
            "summary": summary,
            "findings": [
                {
                    "title": blocker.get("title", "Action target missing"),
                    "detail": detail,
                    "severity": "info",
                    "root_cause": "",
                    "affected_products": [],
                    "affected_regions": [],
                }
            ],
            "recommendations": [
                {
                    "action_type": blocker.get("action_type", "provide_product_id"),
                    "reason": recommendation,
                    "risk_level": "low",
                    "reversible": True,
                }
            ],
            "actions_taken": [],
            "pending_approvals": [],
        },
        "messages": [AIMessage(content=summary)],
    }

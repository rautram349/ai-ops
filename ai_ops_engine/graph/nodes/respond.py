"""Graph node — respond: synthesise final natural-language answer."""

from __future__ import annotations

import json
from typing import Any

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ai_ops_engine.graph.nodes.shared import (
    _strip_code_fences,
    _summarise_domain_findings,
    _summarise_tool_results,
)
from ai_ops_engine.graph.state import AgentState
from ai_ops_engine.llm import get_llm
from ai_ops_engine.prompts import RESPOND_SYSTEM as _RESPOND_SYSTEM

logger = structlog.get_logger(__name__)


async def respond(state: AgentState) -> dict:
    """Synthesise all tool results into the final natural-language response."""
    llm = get_llm()

    tool_summary = _summarise_tool_results(state["tool_results"])

    actions_taken = [
        f"{r['tool']} on {r['server']}"
        for r in state["tool_results"]
        if r.get("error") is None
        and r.get("tool")
        in {
            "restock_product",
            "pause_campaign",
            "apply_discount",
            "create_support_ticket",
        }
    ]

    _SKIP_PREFIXES = (
        "[route]",
        "[plan_domains]",
        "[synthesize]",
        "[plan]",
        "[execute]",
        "[memory_agent]",
    )
    prior_msgs = [
        m
        for m in state.get("messages", [])
        if isinstance(m, (HumanMessage, AIMessage))
        and not m.content.startswith(_SKIP_PREFIXES)
        and not any(
            m.content.startswith(f"[{a}]")
            for a in (
                "sales_agent",
                "inventory_agent",
                "marketing_agent",
                "support_agent",
            )
        )
        and m.content != state["user_query"]
    ]

    reflection_summary: str = state.get("reflection_summary") or ""
    reflection_confidence: float = state.get("reflection_confidence") or 1.0

    findings_text = _summarise_domain_findings(state.get("domain_findings") or [])

    respond_content = (
        f"User query: {state['user_query']}\n\n"
        f"Intent: {state['intent']}\n\n"
        f"Domain findings:\n{findings_text}\n\n"
        f"Tool data:\n{tool_summary}\n\n"
        f"Actions taken: {actions_taken or 'none'}"
    )

    if reflection_summary:
        respond_content += (
            f"\n\nReflection context: {reflection_summary}\n"
            f"Evidence confidence: {reflection_confidence:.0%} — adjust the confidence "
            f"of your findings accordingly and explicitly note any gaps if confidence < 70%."
        )

    memory_matches = state.get("memory_matches") or []
    if memory_matches:
        matches_text = json.dumps(memory_matches, default=str, indent=2)
        respond_content += (
            f"\n\nPast incident memory:\n"
            f"{matches_text}"
            "\n\nMemory instruction: include these incidents in the JSON memory_matches "
            "field. Also explicitly mention the most relevant past incident in the "
            "summary or in one finding, while distinguishing current evidence from "
            "historical context."
        )
    elif state.get("intent") == "memory_recall":
        respond_content += "\n\nNo matching past incidents were found in memory."

    response = await llm.ainvoke(
        [SystemMessage(content=_RESPOND_SYSTEM)]
        + prior_msgs[-6:]
        + [HumanMessage(content=respond_content)]
    )

    try:
        cleaned = _strip_code_fences(
            response.content if hasattr(response, "content") else str(response)
        )
        response_dict: dict[str, Any] = json.loads(cleaned)
    except (json.JSONDecodeError, AttributeError):
        response_dict = {
            "summary": response.content
            if hasattr(response, "content")
            else str(response),
            "findings": [],
            "recommendations": [],
            "actions_taken": actions_taken,
        }

    response_dict["actions_taken"] = actions_taken

    recs = response_dict.get("recommendations", [])
    if recs and isinstance(recs[0], str):
        response_dict["recommendations"] = [
            {
                "action_type": "investigate",
                "reason": r,
                "risk_level": "low",
                "reversible": True,
            }
            for r in recs
        ]

    logger.info("respond", intent=state["intent"])

    return {
        "response_summary": response_dict.get("summary", ""),
        "response_details": response_dict,
        "messages": [AIMessage(content=response_dict.get("summary", ""))],
    }

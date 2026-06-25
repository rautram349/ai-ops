"""Graph node — route: classify user intent and apply scope guardrails."""

from __future__ import annotations

import json
import typing

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ai_ops_engine.graph.nodes.guardrails import _local_guardrail, _looks_like_action_request
from ai_ops_engine.graph.nodes.shared import SKIP_MESSAGE_PREFIXES, _now, _strip_code_fences
from ai_ops_engine.graph.state import AgentState, Intent
from ai_ops_engine.llm import get_llm
from ai_ops_engine.prompts import ROUTE_SYSTEM as _ROUTE_SYSTEM

logger = structlog.get_logger(__name__)

_VALID_INTENTS: frozenset[str] = frozenset(typing.get_args(Intent))

def _guardrail_response(category: str, reason: str) -> dict:
    return {
        "intent": "irrelevant",
        "guardrail_status": "blocked",
        "guardrail_category": category,
        "guardrail_reason": reason,
        "messages": [
            AIMessage(
                content=f"[route] Blocked irrelevant prompt. Category: {category}. Reason: {reason}"
            )
        ],
    }


async def route(state: AgentState) -> dict:
    """Classify the user query into a domain intent."""
    t0 = _now()
    llm = get_llm()
    query = state["user_query"]

    blocked, category, reason = _local_guardrail(query)
    if blocked:
        logger.info("route_guardrail_blocked", category=category, reason=reason, query=query[:80])
        return _guardrail_response(category, reason)

    if _looks_like_action_request(query):
        logger.info("route_deterministic_action", query=query[:80], guardrail_category=category)
        return {
            "intent": "action",
            "guardrail_status": "allowed",
            "guardrail_category": category if category != "unknown" else "in_scope",
            "guardrail_reason": reason if category != "unknown" else "Explicit operational action request.",
            "messages": [AIMessage(content="[route] Intent classified as: action")],
        }

    prior_msgs = [
        m for m in state.get("messages", [])
        if isinstance(m, (HumanMessage, AIMessage))
        and not str(m.content).startswith(SKIP_MESSAGE_PREFIXES)
        and m.content != query
    ]

    llm_messages = (
        [SystemMessage(content=_ROUTE_SYSTEM), *prior_msgs[-4:], HumanMessage(content=query)]
    )

    response = await llm.ainvoke(llm_messages)
    t1 = _now()

    raw: str = str(response.content) if hasattr(response, "content") else str(response)
    logger.info(
        "route_raw_response",
        raw=raw[:300],
        query=query[:80],
        latency_ms=int((t1 - t0).total_seconds() * 1000),
    )

    try:
        cleaned = _strip_code_fences(raw)
        parsed = json.loads(cleaned)
        intent: Intent = parsed.get("intent", "unknown")
        guardrail = parsed.get("guardrail") or {}
    except (json.JSONDecodeError, AttributeError) as exc:
        logger.error("route_json_parse_failed", error=str(exc), raw=raw[:300])
        parsed = {}
        intent = "unknown"
        guardrail = {}

    if intent not in _VALID_INTENTS:
        logger.warning("route_invalid_intent", intent=intent, raw=raw[:200])
        intent = "unknown"

    if intent == "irrelevant":
        guardrail_category = str(guardrail.get("category") or "irrelevant")
        guardrail_reason = str(
            guardrail.get("reason")
            or parsed.get("rationale")
            or "Prompt is outside the AI-ops operational scope."
        )
        logger.info(
            "route_guardrail_blocked_llm",
            category=guardrail_category,
            reason=guardrail_reason,
            query=query[:80],
        )
        return _guardrail_response(guardrail_category, guardrail_reason)

    guardrail_category = category if category != "unknown" else str(guardrail.get("category") or "in_scope")
    guardrail_reason = reason if category != "unknown" else str(guardrail.get("reason") or "Allowed by route classifier.")

    logger.info("route", intent=intent, query=query[:80], guardrail_category=guardrail_category)

    return {
        "intent": intent,
        "guardrail_status": "allowed",
        "guardrail_category": guardrail_category,
        "guardrail_reason": guardrail_reason,
        "messages": [AIMessage(content=f"[route] Intent classified as: {intent}")],
    }

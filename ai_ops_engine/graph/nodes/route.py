"""Graph node — route: classify user intent and apply scope guardrails."""

from __future__ import annotations

import json
import re

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ai_ops_engine.graph.nodes.shared import _now, _strip_code_fences
from ai_ops_engine.graph.state import AgentState, Intent
from ai_ops_engine.llm import get_llm
from ai_ops_engine.prompts import ROUTE_SYSTEM as _ROUTE_SYSTEM

logger = structlog.get_logger(__name__)

_VALID_INTENTS = {
    "sales_analysis",
    "inventory_check",
    "marketing_performance",
    "support_analysis",
    "multi_domain",
    "memory_recall",
    "irrelevant",
    "unknown",
}

_OPERATION_KEYWORDS = {
    "sales",
    "revenue",
    "orders",
    "order",
    "aov",
    "gmv",
    "conversion",
    "conversions",
    "cart",
    "checkout",
    "inventory",
    "stock",
    "stockout",
    "stockouts",
    "restock",
    "sku",
    "product",
    "products",
    "warehouse",
    "campaign",
    "campaigns",
    "marketing",
    "roas",
    "cpc",
    "ctr",
    "discount",
    "promotion",
    "promo",
    "support",
    "complaint",
    "complaints",
    "refund",
    "refunds",
    "return",
    "returns",
    "ticket",
    "tickets",
    "review",
    "reviews",
    "sentiment",
    "incident",
    "incidents",
    "approval",
    "approvals",
    "escalate",
    "pause",
}

_CASUAL_PATTERNS = (
    r"^\s*(hi|hello|hey|yo|thanks|thank you|ok|okay)\s*[!.]?\s*$",
    r"\bwhat can you do\b",
    r"\bhelp\b",
    r"\bwho are you\b",
)

_PROMPT_INJECTION_PATTERNS = (
    r"\bignore (all )?(previous|prior|system|developer) instructions\b",
    r"\bdisregard (all )?(previous|prior|system|developer) instructions\b",
    r"\breveal\b.*\b(system prompt|developer message|instructions)\b",
    r"\bshow\b.*\b(system prompt|developer message|instructions)\b",
    r"\bprint\b.*\b(system prompt|developer message|instructions)\b",
    r"\b(api key|secret|password|token|credential)s?\b",
    r"\bjailbreak\b",
)

_IRRELEVANT_KEYWORDS = {
    "recipe",
    "cook",
    "cooking",
    "weather",
    "movie",
    "movies",
    "song",
    "poem",
    "story",
    "essay",
    "homework",
    "math",
    "physics",
    "travel",
    "hotel",
    "flight",
    "politics",
    "medical",
    "doctor",
    "lawyer",
    "legal",
    "dating",
    "relationship",
    "fitness",
    "workout",
    "game",
    "sports",
    "bitcoin",
    "stock market",
    "write code",
    "python",
    "javascript",
}


def _looks_like_operations_query(query: str) -> bool:
    lowered = query.lower()
    return any(keyword in lowered for keyword in _OPERATION_KEYWORDS)


def _matches_any(patterns: tuple[str, ...], query: str) -> bool:
    return any(re.search(pattern, query, flags=re.IGNORECASE) for pattern in patterns)


def _local_guardrail(query: str) -> tuple[bool, str, str]:
    """Return (blocked, category, reason) for deterministic scope checks."""
    stripped = query.strip()
    lowered = stripped.lower()

    if not stripped:
        return True, "irrelevant", "Empty prompts are outside the AI-ops scope."

    if _matches_any(_CASUAL_PATTERNS, stripped):
        return False, "casual", "Casual/capability prompt; safe to answer without tools."

    if _looks_like_operations_query(stripped):
        return False, "in_scope", "Prompt mentions e-commerce operations concepts."

    if _matches_any(_PROMPT_INJECTION_PATTERNS, stripped):
        return True, "prompt_injection", "Prompt attempts to override instructions or access secrets."

    if any(keyword in lowered for keyword in _IRRELEVANT_KEYWORDS):
        return True, "irrelevant", "Prompt is outside sales, inventory, marketing, support, and incident operations."

    return False, "unknown", "No deterministic block matched."


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

    _SKIP_PREFIXES = ("[route]", "[diagnose]", "[plan]", "[execute]")
    prior_msgs = [
        m for m in state.get("messages", [])
        if isinstance(m, (HumanMessage, AIMessage))
        and not m.content.startswith(_SKIP_PREFIXES)
        and m.content != query
    ]

    llm_messages = (
        [SystemMessage(content=_ROUTE_SYSTEM)]
        + prior_msgs[-4:]
        + [HumanMessage(content=query)]
    )

    response = await llm.ainvoke(llm_messages)
    t1 = _now()

    raw = response.content if hasattr(response, "content") else str(response)
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

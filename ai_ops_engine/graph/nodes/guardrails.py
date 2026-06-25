"""Deterministic scope-checking guardrails for the route node."""

from __future__ import annotations

import re

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
    "apply",
    "create ticket",
    "go ahead",
    "fix it",
    "make it happen",
    "approve",
    "reject",
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

_ACTION_PATTERNS = (
    r"\b(restock|replenish|reorder)\b",
    r"\bapply\b.*\b(discount|promotion|promo)\b",
    r"\bpause\b.*\b(campaign|campaigns)\b",
    r"\b(create|open)\b.*\b(support )?(ticket|tickets)\b",
    r"\b(go ahead|fix it|make it happen)\b",
    r"\b(approve|reject)\b",
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


def _looks_like_action_request(query: str) -> bool:
    """Deterministically catch explicit write-operation requests."""
    return _matches_any(_ACTION_PATTERNS, query)


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

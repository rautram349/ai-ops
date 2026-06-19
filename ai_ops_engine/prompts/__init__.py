"""All LLM prompts loaded from individual .md files.

Each constant is a system prompt string. Agent prompts contain a ``{today}``
placeholder that is substituted at runtime by ``ai_ops_engine.agents.base``.
"""

from ai_ops_engine.prompts.loader import load_prompt

# ── Node prompts ──────────────────────────────────────────────────────────────
ROUTE_SYSTEM = load_prompt("route")
RECALL_KEYWORD_SYSTEM = load_prompt("recall_keyword")
PLAN_DOMAINS_SYSTEM = load_prompt("plan_domains")
SYNTHESIZE_SYSTEM = load_prompt("synthesize")
REFLECT_SYSTEM = load_prompt("reflect")
PLAN_SYSTEM = load_prompt("plan")
RESPOND_SYSTEM = load_prompt("respond")
UNKNOWN_SYSTEM = load_prompt("unknown")
MEMORY_SYSTEM = load_prompt("memory")

# ── Agent prompts ─────────────────────────────────────────────────────────────
SALES_SYSTEM = load_prompt("sales")
INVENTORY_SYSTEM = load_prompt("inventory")
MARKETING_SYSTEM = load_prompt("marketing")
SUPPORT_SYSTEM = load_prompt("support")

__all__ = [
    "ROUTE_SYSTEM",
    "RECALL_KEYWORD_SYSTEM",
    "PLAN_DOMAINS_SYSTEM",
    "SYNTHESIZE_SYSTEM",
    "REFLECT_SYSTEM",
    "PLAN_SYSTEM",
    "RESPOND_SYSTEM",
    "UNKNOWN_SYSTEM",
    "MEMORY_SYSTEM",
    "SALES_SYSTEM",
    "INVENTORY_SYSTEM",
    "MARKETING_SYSTEM",
    "SUPPORT_SYSTEM",
]

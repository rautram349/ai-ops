"""Single source of truth for domain ↔ server ↔ agent mappings.

Adding a new domain means editing only this file.
"""

from __future__ import annotations

DOMAINS: frozenset[str] = frozenset({"sales", "inventory", "marketing", "support"})

DOMAIN_TO_SERVER: dict[str, str] = {
    "sales": "metrics",
    "inventory": "inventory",
    "marketing": "marketing",
    "support": "support",
}

SERVER_TO_DOMAIN: dict[str, str] = {v: k for k, v in DOMAIN_TO_SERVER.items()}

DOMAIN_TO_AGENT: dict[str, str] = {
    "sales": "sales_agent",
    "inventory": "inventory_agent",
    "marketing": "marketing_agent",
    "support": "support_agent",
}

AGENT_TO_DOMAIN: dict[str, str] = {v: k for k, v in DOMAIN_TO_AGENT.items()}

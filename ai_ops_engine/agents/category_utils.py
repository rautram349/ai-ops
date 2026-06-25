"""Shared category keyword→DB-name mapping for inventory and support agents."""

from __future__ import annotations

_CATEGORY_ALIASES: dict[str, str] = {
    "electronics": "Electronics",
    "clothing": "Clothing",
    "apparel": "Clothing",
    "fashion": "Clothing",
    "home": "Home & Kitchen",
    "kitchen": "Home & Kitchen",
    "beauty": "Beauty & Personal Care",
    "personal care": "Beauty & Personal Care",
    "skincare": "Beauty & Personal Care",
    "sports": "Sports & Outdoors",
    "outdoors": "Sports & Outdoors",
    "outdoor": "Sports & Outdoors",
    "fitness": "Sports & Outdoors",
    "books": "Books & Media",
    "media": "Books & Media",
}


def _extract_category(query: str) -> str | None:
    """Return the canonical DB category for the first matching keyword in query."""
    q_lower = query.lower()
    for keyword, category in _CATEGORY_ALIASES.items():
        if keyword in q_lower:
            return category
    return None

"""Deterministic restock-request parsing helpers for the plan node."""

from __future__ import annotations

import re

import structlog

from ai_ops_engine.clients.mcp_client import get_mcp_client
from ai_ops_engine.graph.state import PendingApproval

logger = structlog.get_logger(__name__)

_RESTOCK_RE = re.compile(r"\b(restock|replenish|reorder)\b", re.IGNORECASE)
_PRODUCT_ID_RE = re.compile(r"\bPROD\s*-?\s*(\d{1,4})\b", re.IGNORECASE)
_RESTOCK_DEFAULT_PRIORITY = "normal"
_REGION_RE = re.compile(r"\b(North|South|East|West)\b", re.IGNORECASE)
_QUANTITY_PATTERNS = (
    re.compile(r"\b(?:quantity|qty)\s*[:=]?\s*(\d+)\b", re.IGNORECASE),
    re.compile(r"\b(\d+)\s*(?:units?|pcs|pieces)\b", re.IGNORECASE),
    re.compile(r"\brestock\s+(\d+)\s+(?:of\s+)?", re.IGNORECASE),
)


def _is_restock_request(query: str) -> bool:
    return bool(_RESTOCK_RE.search(query))


def _extract_product_ids(query: str) -> list[str]:
    seen: set[str] = set()
    ids: list[str] = []
    for match in _PRODUCT_ID_RE.finditer(query):
        pid = f"PROD-{int(match.group(1)):03d}"
        if pid not in seen:
            seen.add(pid)
            ids.append(pid)
    return ids


def _blocker(
    *,
    summary: str,
    detail: str,
    recommendation: str,
    title: str = "Restock target missing",
    action_type: str = "provide_product_id",
) -> dict:
    return {
        "summary": summary,
        "title": title,
        "detail": detail,
        "recommendation": recommendation,
        "action_type": action_type,
    }


def _extract_region(query: str) -> str | None:
    match = _REGION_RE.search(query)
    if not match:
        return None
    return match.group(1).title()


def _extract_quantity(query: str) -> int | None:
    for pattern in _QUANTITY_PATTERNS:
        match = pattern.search(query)
        if not match:
            continue
        quantity = int(match.group(1))
        if quantity > 0:
            return quantity
    return None


async def _resolve_restock_product_ids(query: str) -> tuple[list[str], dict | None]:
    """Resolve explicit product IDs or exact product names for restock requests."""
    explicit = _extract_product_ids(query)
    if explicit:
        return explicit, None

    client = get_mcp_client()
    try:
        result = await client.call_tool(
            "inventory",
            "resolve_products",
            {"text": query, "limit": 5},
        )
    except Exception as exc:
        logger.warning("restock_product_resolution_failed", error=str(exc))
        return [], _blocker(
            summary="No restock approval was created because the product target could not be verified.",
            detail=(
                "The request asks for a restock, but product resolution failed. "
                "No explicit product ID was provided."
            ),
            recommendation="Provide a specific product ID such as PROD-063 and try again.",
        )

    matches = result.get("matches", []) if isinstance(result, dict) else []
    if len(matches) == 1:
        pid = matches[0].get("product_id")
        return ([pid] if pid else []), None
    if len(matches) > 1:
        names = ", ".join(
            f"{m.get('product_id')} ({m.get('product_name')})" for m in matches[:5]
        )
        return [], _blocker(
            summary="No restock approval was created because the product name is ambiguous.",
            detail=(
                "The request asks for a restock, but multiple products matched the text: "
                f"{names}."
            ),
            recommendation="Provide one specific product ID, for example PROD-063.",
        )
    return [], _blocker(
        summary="No restock approval was created because no explicit product ID or recognized product name was mentioned.",
        detail=(
            "The request asks for a restock, but it does not include a specific product ID "
            "or a product name that can be matched to the catalog."
        ),
        recommendation="Provide a specific product ID or recognized product name, then request the restock again.",
    )


def _missing_restock_args_blocker(
    *,
    product_ids: list[str],
    region: str | None,
    quantity: int | None,
) -> dict | None:
    missing = []
    if not region:
        missing.append("region")
    if quantity is None:
        missing.append("quantity")
    if not missing:
        return None

    pid_text = ", ".join(product_ids)
    missing_text = " and ".join(missing)
    return _blocker(
        summary=(
            f"No restock approval was created because no {missing_text} "
            f"was mentioned for {pid_text}."
        ),
        detail=(
            f"The restock request identifies {pid_text}, but the "
            f"restock_product action also requires an explicit region "
            f"(North, South, East, or West) and quantity."
        ),
        recommendation=(
            f"Provide the missing {missing_text}, for example: "
            f"'Restock 100 units of {product_ids[0]} in North'."
        ),
        title="Restock details missing",
        action_type="provide_restock_details",
    )


def _build_restock_approvals(
    product_ids: list[str],
    *,
    region: str,
    quantity: int,
) -> list[PendingApproval]:
    approvals: list[PendingApproval] = []
    for pid in product_ids:
        approvals.append(
            PendingApproval(
                tool="restock_product",
                server="inventory",
                arguments={
                    "product_id": pid,
                    "region": region,
                    "quantity": quantity,
                    "priority": _RESTOCK_DEFAULT_PRIORITY,
                },
                reason=(
                    f"Restock approval prepared for {quantity} units of "
                    f"{pid} in {region}."
                ),
                risk_level="high",
                reversible=True,
            )
        )
    return approvals

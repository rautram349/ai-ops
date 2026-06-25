"""Scheduled health-monitor service.

``run_monitor_check`` is the core function called by the APScheduler job.  It:

1. Derives the *check_date* from the latest date in the ``orders`` table.
2. Calls four MCP tools in parallel (revenue anomaly, order anomaly, stockout
   events, complaint summary).
3. Classifies each result into a typed incident.
4. Deduplicates — skips creation if an incident of the same type already exists
   for that date.
5. Persists new ``Incident`` rows and returns a ``MonitorResult`` summary.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_ops_engine.clients.mcp_client import get_mcp_client
from backend.db.repositories import IncidentRepository

logger = structlog.get_logger(__name__)


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class AnomalyDetail:
    incident_type: str
    title: str
    summary: str
    affected_domains: list[str]
    root_causes: list[dict[str, Any]]
    affected_products: list[str] | None = None
    confidence: float = 0.7


@dataclass
class MonitorResult:
    check_date: date
    anomalies_found: int = 0
    incidents_created: int = 0
    detail: list[dict[str, Any]] = field(default_factory=list)


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_check_date(db: AsyncSession) -> date:
    """Return the latest date present in the orders table."""
    row = await db.execute(text("SELECT MAX(created_date) FROM orders"))
    result = row.scalar_one_or_none()
    if result is None:
        return date.today()
    if isinstance(result, date):
        return result
    return date.fromisoformat(str(result))


def _as_float(value: Any) -> float | None:
    """Best-effort float coercion for MCP payload values."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    """Best-effort integer coercion for MCP payload values."""
    numeric = _as_float(value)
    if numeric is None:
        return None
    return int(numeric)


def _format_float(value: Any, decimals: int = 2) -> str:
    """Format a numeric value or return a placeholder for missing data."""
    numeric = _as_float(value)
    if numeric is None:
        return "?"
    return f"{numeric:.{decimals}f}"


def _format_int(value: Any) -> str:
    """Format an integer-ish value or return a placeholder."""
    numeric = _as_int(value)
    if numeric is None:
        return "?"
    return str(numeric)


def _normalize_parallel_result(result: Any, *, server: str, tool_name: str) -> Any:
    """Log parallel MCP failures and return a safe value for classification."""
    if isinstance(result, Exception):
        logger.warning(
            "monitor_check.tool_failed",
            server=server,
            tool_name=tool_name,
            error=str(result),
        )
        return None
    return result


def _classify_revenue_anomaly(result: Any, check_date: date) -> AnomalyDetail | None:
    if not isinstance(result, dict):
        return None
    if not result.get("is_anomaly"):
        return None
    severity = result.get("severity", "unknown")
    z = _as_float(result.get("z_score"))
    direction = result.get("anomaly_direction", "")
    actual = _format_float(result.get("date_value"))
    baseline = _format_float(result.get("baseline_mean"))
    z_display = _format_float(z)
    return AnomalyDetail(
        incident_type="revenue_anomaly",
        title=f"Revenue anomaly on {check_date}: {direction} (severity: {severity})",
        summary=(
            f"Revenue on {check_date} was {actual} vs baseline {baseline} "
            f"(z={z_display}, {severity}). Anomaly direction: {direction}."
        ),
        affected_domains=["metrics"],
        root_causes=[
            {
                "cause": f"Revenue deviated {direction} with z-score {z_display}",
                "confidence": 0.85,
                "domains": ["metrics"],
            }
        ],
        confidence=0.85,
    )


def _classify_order_anomaly(result: Any, check_date: date) -> AnomalyDetail | None:
    if not isinstance(result, dict):
        return None
    if not result.get("is_anomaly"):
        return None
    severity = result.get("severity", "unknown")
    z = _as_float(result.get("z_score"))
    direction = result.get("anomaly_direction", "")
    actual = _format_int(result.get("date_value"))
    baseline = _format_float(result.get("baseline_mean"), 1)
    z_display = _format_float(z)
    return AnomalyDetail(
        incident_type="order_anomaly",
        title=f"Order volume anomaly on {check_date}: {direction} (severity: {severity})",
        summary=(
            f"Order count on {check_date} was {actual} vs baseline {baseline} "
            f"(z={z_display}, {severity}). Anomaly direction: {direction}."
        ),
        affected_domains=["metrics"],
        root_causes=[
            {
                "cause": f"Order volume deviated {direction} with z-score {z_display}",
                "confidence": 0.8,
                "domains": ["metrics"],
            }
        ],
        confidence=0.8,
    )


def _classify_stockout(result: Any, check_date: date) -> AnomalyDetail | None:
    if not isinstance(result, dict):
        return None
    events: list[dict] = result.get("stockout_events", [])
    if not events:
        return None
    lost_rev = _format_float(result.get("total_lost_revenue_estimate"))
    products = [e.get("product_name", e.get("product_id", "?")) for e in events[:5]]
    return AnomalyDetail(
        incident_type="stockout",
        title=f"{len(events)} stockout event(s) detected on {check_date}",
        summary=(
            f"{len(events)} stockout event(s) on {check_date}. "
            f"Estimated lost revenue: ${lost_rev}. "
            f"Affected products: {', '.join(products)}."
        ),
        affected_domains=["inventory"],
        root_causes=[
            {
                "cause": f"{len(events)} products went out of stock",
                "confidence": 0.9,
                "domains": ["inventory"],
            }
        ],
        affected_products=[e["product_id"] for e in events if e.get("product_id")],
        confidence=0.9,
    )


def _classify_complaint_spike(result: Any, check_date: date) -> AnomalyDetail | None:
    if not isinstance(result, dict):
        return None
    total = _as_int(result.get("total_tickets"))
    if total is None or total == 0:
        return None
    comparison = result.get("period_comparison", {})
    prev_total = _as_float(comparison.get("prev_total"))
    change_pct = _as_float(comparison.get("change_pct"))

    # Only flag as anomaly if tickets increased significantly vs prior period
    if prev_total is not None and total <= prev_total * 1.5:
        return None

    change_str = f" (+{change_pct:.1f}% vs prior period)" if change_pct is not None else ""
    return AnomalyDetail(
        incident_type="complaint_spike",
        title=f"Complaint spike on {check_date}: {total} tickets{change_str}",
        summary=(
            f"{total} support tickets on {check_date}{change_str}. "
            f"This is above the 1.5x threshold relative to the prior period."
        ),
        affected_domains=["support"],
        root_causes=[
            {
                "cause": f"Support ticket volume reached {total}{change_str}",
                "confidence": 0.75,
                "domains": ["support"],
            }
        ],
        confidence=0.75,
    )


# ── Core check ────────────────────────────────────────────────────────────────

async def run_monitor_check(db: AsyncSession) -> MonitorResult:
    """Run the full health check for the latest data date."""
    check_date = await _get_check_date(db)
    date_str = check_date.isoformat()

    logger.info("monitor_check.start", check_date=date_str)
    t0 = time.monotonic()

    # ── Parallel MCP calls ────────────────────────────────────────────────────
    client = get_mcp_client()
    calls: list[tuple[str, str, dict[str, Any]]] = [
        ("metrics", "detect_anomaly", {"metric": "revenue", "date": date_str}),
        ("metrics", "detect_anomaly", {"metric": "orders", "date": date_str}),
        ("inventory", "get_stockout_events", {"start_date": date_str, "end_date": date_str}),
        ("support", "get_complaint_summary", {"start_date": date_str, "end_date": date_str}),
    ]
    raw_results = await client.call_tools_parallel(calls)
    normalized_results = [
        _normalize_parallel_result(result, server=server, tool_name=tool_name)
        for (server, tool_name, _), result in zip(calls, raw_results, strict=False)
    ]

    # ── Classify ──────────────────────────────────────────────────────────────
    classifiers = [
        _classify_revenue_anomaly(normalized_results[0], check_date),
        _classify_order_anomaly(normalized_results[1], check_date),
        _classify_stockout(normalized_results[2], check_date),
        _classify_complaint_spike(normalized_results[3], check_date),
    ]
    anomalies = [a for a in classifiers if a is not None]

    # ── Persist (with deduplication) ──────────────────────────────────────────
    repo = IncidentRepository(db)
    incidents_created = 0
    detail: list[dict[str, Any]] = []

    for anomaly in anomalies:
        already_exists = await repo.exists_for_date_type(anomaly.incident_type, check_date)
        action = "skipped_duplicate" if already_exists else "created"

        if not already_exists:
            await repo.create(
                conversation_id=None,
                incident_date=check_date,
                incident_type=anomaly.incident_type,
                title=anomaly.title,
                summary=anomaly.summary,
                affected_domains=anomaly.affected_domains,
                root_causes=anomaly.root_causes,
                affected_products=anomaly.affected_products,
                confidence=anomaly.confidence,
            )
            incidents_created += 1

        detail.append(
            {
                "incident_type": anomaly.incident_type,
                "title": anomaly.title,
                "action": action,
            }
        )
        logger.info(
            "monitor_check.incident",
            incident_type=anomaly.incident_type,
            action=action,
        )

    await db.commit()

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "monitor_check.done",
        check_date=date_str,
        anomalies_found=len(anomalies),
        incidents_created=incidents_created,
        duration_ms=elapsed_ms,
    )

    return MonitorResult(
        check_date=check_date,
        anomalies_found=len(anomalies),
        incidents_created=incidents_created,
        detail=detail,
    )

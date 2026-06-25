"""Metrics MCP Server — 5 read-only analytical tools.

Tools
-----
- get_sales_summary        aggregate orders by date / region / category
- compare_sales            two-period comparison with % change
- get_revenue_by_product   top-N products by revenue / units / orders
- get_revenue_by_region    revenue breakdown across regions
- detect_anomaly           z-score anomaly detection on daily metrics

Run this server::

    python -m mcp_servers.metrics.server
"""

from __future__ import annotations

import os
import statistics

from dotenv import load_dotenv
from fastmcp import FastMCP

from mcp_servers.db import execute_query, safe_date

load_dotenv()

mcp = FastMCP("metrics-mcp")

_HOST = os.environ.get("MCP_METRICS_HOST", "localhost")
_PORT = int(os.environ.get("MCP_METRICS_PORT", "5010"))

# ─────────────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────────────

def _pct_change(old: float, new: float) -> float | None:
    if old == 0:
        return None
    return round((new - old) / old * 100, 2)


def _sales_agg(start: str, end: str, region: str | None, category: str | None) -> dict:
    """Return core sales aggregates for the given window."""
    filters = ["o.created_date BETWEEN %(start)s AND %(end)s"]
    params: dict = {"start": start, "end": end}

    if region:
        filters.append("o.region = %(region)s")
        params["region"] = region
    if category:
        filters.append("p.category = %(category)s")
        params["category"] = category

    where = " AND ".join(filters)

    join = "JOIN order_items oi ON oi.order_id = o.order_id JOIN products p ON p.product_id = oi.product_id" if category else ""

    sql = f"""
        SELECT
            COUNT(DISTINCT o.order_id)   AS total_orders,
            SUM(o.final_value)           AS total_revenue,
            SUM(o.discount_amount)       AS total_discount,
            COUNT(DISTINCT o.customer_id) AS unique_customers
        FROM orders o
        {join}
        WHERE {where}
    """
    rows = execute_query(sql, params)
    row = rows[0] if rows else {}

    total_orders = int(row.get("total_orders") or 0)
    total_revenue = float(row.get("total_revenue") or 0)
    total_discount = float(row.get("total_discount") or 0)
    unique_customers = int(row.get("unique_customers") or 0)

    return {
        "total_orders": total_orders,
        "total_revenue": round(total_revenue, 2),
        "total_discount": round(total_discount, 2),
        "net_revenue": round(total_revenue - total_discount, 2),
        "average_order_value": round(total_revenue / total_orders, 2) if total_orders else 0.0,
        "unique_customers": unique_customers,
    }


# ─────────────────────────────────────────────────────────────────────────────
# tools
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def get_sales_summary(
    start_date: str,
    end_date: str | None = None,
    region: str | None = None,
    category: str | None = None,
) -> dict:
    """Get sales summary metrics for a date or date range."""
    start_date = safe_date(start_date)
    end = safe_date(end_date) or start_date

    agg = _sales_agg(start_date, end, region, category)

    # breakdown by region
    region_sql = """
        SELECT
            o.region,
            COUNT(DISTINCT o.order_id)    AS orders,
            ROUND(SUM(o.final_value)::numeric, 2) AS revenue
        FROM orders o
        WHERE o.created_date BETWEEN %(start)s AND %(end)s
        GROUP BY o.region
        ORDER BY revenue DESC
    """
    by_region = execute_query(region_sql, {"start": start_date, "end": end})

    # breakdown by category (always shown)
    # Use oi.line_total (item-level) to avoid double-counting o.final_value
    # across multiple categories when a single order spans several categories.
    cat_sql = """
        SELECT
            p.category,
            COUNT(DISTINCT o.order_id)                    AS orders,
            ROUND(SUM(oi.line_total)::numeric, 2)         AS revenue
        FROM orders o
        JOIN order_items oi ON oi.order_id = o.order_id
        JOIN products p     ON p.product_id = oi.product_id
        WHERE o.created_date BETWEEN %(start)s AND %(end)s
        GROUP BY p.category
        ORDER BY revenue DESC
    """
    by_category = execute_query(cat_sql, {"start": start_date, "end": end})

    return {
        "period": {"start": start_date, "end": end},
        **agg,
        "by_region": [dict(r) for r in by_region],
        "by_category": [dict(r) for r in by_category],
    }


@mcp.tool()
def compare_sales(
    period_a_start: str,
    period_a_end: str,
    period_b_start: str,
    period_b_end: str,
    dimensions: list[str] | None = None,
) -> dict:
    """Compare sales metrics between two time periods."""
    period_a_start = safe_date(period_a_start)
    period_a_end = safe_date(period_a_end)
    period_b_start = safe_date(period_b_start)
    period_b_end = safe_date(period_b_end)
    # Normalize: period_a is always the earlier/baseline period so that
    # positive change_pct means the later period (period_b) improved.
    if (period_a_start or "") > (period_b_start or ""):
        period_a_start, period_b_start = period_b_start, period_a_start
        period_a_end,   period_b_end   = period_b_end,   period_a_end

    pa = _sales_agg(period_a_start, period_a_end, None, None)  # baseline (earlier)
    pb = _sales_agg(period_b_start, period_b_end, None, None)  # current  (later)

    changes = {
        "orders_change_pct": _pct_change(pa["total_orders"], pb["total_orders"]),
        "revenue_change_pct": _pct_change(pa["total_revenue"], pb["total_revenue"]),
        "aov_change_pct": _pct_change(pa["average_order_value"], pb["average_order_value"]),
    }

    by_dimension: list[dict] = []
    dims = dimensions or []

    if "region" in dims:
        sql = """
            SELECT
                o.region                                     AS dimension_value,
                'region'                                     AS dimension,
                SUM(CASE WHEN o.created_date BETWEEN %(as)s AND %(ae)s THEN o.final_value ELSE 0 END) AS period_a_revenue,
                SUM(CASE WHEN o.created_date BETWEEN %(bs)s AND %(be)s THEN o.final_value ELSE 0 END) AS period_b_revenue
            FROM orders o
            WHERE o.created_date BETWEEN %(as)s AND %(be)s
            GROUP BY o.region
            ORDER BY period_b_revenue DESC
        """
        rows = execute_query(sql, {"as": period_a_start, "ae": period_a_end,
                                   "bs": period_b_start, "be": period_b_end})
        for r in rows:
            r2 = dict(r)
            r2["change_pct"] = _pct_change(float(r2["period_a_revenue"] or 0),
                                            float(r2["period_b_revenue"] or 0))
            by_dimension.append(r2)

    if "category" in dims:
        # Use oi.line_total to avoid double-counting order-level value across categories
        sql = """
            SELECT
                p.category                                   AS dimension_value,
                'category'                                   AS dimension,
                ROUND(SUM(CASE WHEN o.created_date BETWEEN %(as)s AND %(ae)s THEN oi.line_total ELSE 0 END)::numeric, 2) AS period_a_revenue,
                ROUND(SUM(CASE WHEN o.created_date BETWEEN %(bs)s AND %(be)s THEN oi.line_total ELSE 0 END)::numeric, 2) AS period_b_revenue
            FROM orders o
            JOIN order_items oi ON oi.order_id = o.order_id
            JOIN products p     ON p.product_id = oi.product_id
            WHERE o.created_date BETWEEN %(as)s AND %(be)s
            GROUP BY p.category
            ORDER BY period_b_revenue DESC
        """
        rows = execute_query(sql, {"as": period_a_start, "ae": period_a_end,
                                   "bs": period_b_start, "be": period_b_end})
        for r in rows:
            r2 = dict(r)
            r2["change_pct"] = _pct_change(float(r2["period_a_revenue"] or 0),
                                            float(r2["period_b_revenue"] or 0))
            by_dimension.append(r2)

    if "product" in dims:
        sql = """
            SELECT
                p.product_id                                                   AS dimension_value,
                p.name                                                         AS product_name,
                'product'                                                      AS dimension,
                SUM(CASE WHEN o.created_date BETWEEN %(as)s AND %(ae)s THEN oi.line_total ELSE 0 END) AS period_a_revenue,
                SUM(CASE WHEN o.created_date BETWEEN %(bs)s AND %(be)s THEN oi.line_total ELSE 0 END) AS period_b_revenue
            FROM orders o
            JOIN order_items oi ON oi.order_id = o.order_id
            JOIN products p     ON p.product_id = oi.product_id
            WHERE o.created_date BETWEEN %(as)s AND %(be)s
            GROUP BY p.product_id, p.name
            ORDER BY period_b_revenue DESC
            LIMIT 20
        """
        rows = execute_query(sql, {"as": period_a_start, "ae": period_a_end,
                                   "bs": period_b_start, "be": period_b_end})
        for r in rows:
            r2 = dict(r)
            r2["change_pct"] = _pct_change(float(r2["period_a_revenue"] or 0),
                                            float(r2["period_b_revenue"] or 0))
            by_dimension.append(r2)

    return {
        "period_a": {"start": period_a_start, "end": period_a_end, "label": "baseline", **pa},
        "period_b": {"start": period_b_start, "end": period_b_end, "label": "comparison", **pb},
        "changes": changes,
        "change_note": "Positive values mean period_b (later) improved over period_a (baseline/earlier)",
        "by_dimension": by_dimension,
    }


@mcp.tool()
def get_revenue_by_product(
    start_date: str,
    end_date: str | None = None,
    top_n: int = 10,
    sort_by: str = "revenue",
) -> dict:
    """Get revenue breakdown by product for a date range."""
    start_date = safe_date(start_date)
    end = safe_date(end_date) or start_date

    sort_col = {
        "revenue": "total_revenue",
        "units":   "total_units",
        "orders":  "total_orders",
    }.get(sort_by, "total_revenue")

    sql = f"""
        SELECT
            p.product_id,
            p.name                                         AS product_name,
            p.category,
            COUNT(DISTINCT o.order_id)                     AS total_orders,
            SUM(oi.quantity)                               AS total_units,
            ROUND(SUM(oi.line_total)::numeric, 2)          AS total_revenue
        FROM order_items oi
        JOIN orders o   ON o.order_id   = oi.order_id
        JOIN products p ON p.product_id = oi.product_id
        WHERE o.created_date BETWEEN %(start)s AND %(end)s
        GROUP BY p.product_id, p.name, p.category
        ORDER BY {sort_col} DESC
        LIMIT %(top_n)s
    """
    rows = execute_query(sql, {"start": start_date, "end": end, "top_n": top_n})
    return {
        "period": {"start": start_date, "end": end},
        "sort_by": sort_by,
        "products": [dict(r) for r in rows],
    }


@mcp.tool()
def get_revenue_by_region(
    start_date: str,
    end_date: str | None = None,
) -> dict:
    """Get revenue breakdown by region for a date range."""
    start_date = safe_date(start_date)
    end = safe_date(end_date) or start_date

    sql = """
        SELECT
            o.region,
            COUNT(DISTINCT o.order_id)              AS total_orders,
            COUNT(DISTINCT o.customer_id)           AS unique_customers,
            ROUND(SUM(o.final_value)::numeric, 2)   AS total_revenue,
            ROUND(SUM(o.discount_amount)::numeric, 2) AS total_discount,
            ROUND(AVG(o.final_value)::numeric, 2)   AS avg_order_value
        FROM orders o
        WHERE o.created_date BETWEEN %(start)s AND %(end)s
        GROUP BY o.region
        ORDER BY total_revenue DESC
    """
    rows = execute_query(sql, {"start": start_date, "end": end})
    return {
        "period": {"start": start_date, "end": end},
        "regions": [dict(r) for r in rows],
    }


@mcp.tool()
def detect_anomaly(
    metric: str,
    date: str,
    lookback_days: int = 14,
) -> dict:
    """Detect if a metric value is anomalous compared to recent history via z-score."""
    date = safe_date(date)    # Map metric → SQL expression over daily_traffic or orders
    metric_map = {
        "revenue":     ("SELECT created_date AS d, SUM(final_value) AS v FROM orders GROUP BY created_date", "orders"),
        "orders":      ("SELECT created_date AS d, COUNT(*) AS v FROM orders GROUP BY created_date", "orders"),
        "aov":         ("SELECT created_date AS d, AVG(final_value) AS v FROM orders GROUP BY created_date", "orders"),
        "bounce_rate": ("SELECT date AS d, AVG(bounce_rate) AS v FROM daily_traffic GROUP BY date", "daily_traffic"),
    }

    if metric not in metric_map:
        return {"error": f"Unknown metric '{metric}'. Choose from: {list(metric_map)}"}

    base_sql, _ = metric_map[metric]

    # Fetch the target day's value
    target_sql = f"""
        WITH base AS ({base_sql})
        SELECT v FROM base WHERE d = %(date)s
    """
    target_rows = execute_query(target_sql, {"date": date})
    if not target_rows:
        return {"error": f"No data found for metric '{metric}' on {date}"}

    date_value = float(target_rows[0]["v"] or 0)

    # Fetch lookback window (exclude the target date itself)
    history_sql = f"""
        WITH base AS ({base_sql})
        SELECT v FROM base
        WHERE d < %(date)s AND d >= (%(date)s::date - %(days)s)
    """
    history_rows = execute_query(history_sql, {"date": date, "days": lookback_days})
    history = [float(r["v"] or 0) for r in history_rows]

    if len(history) < 3:
        return {
            "metric": metric,
            "date": date,
            "date_value": round(date_value, 4),
            "is_anomaly": False,
            "severity": "none",
            "anomaly_direction": "normal",
            "note": "Insufficient history for z-score calculation",
        }

    mean = statistics.mean(history)
    stddev = statistics.pstdev(history)

    if stddev == 0:
        z_score = 0.0
    else:
        z_score = (date_value - mean) / stddev

    abs_z = abs(z_score)
    is_anomaly = abs_z >= 2.0
    severity = "none"
    if abs_z >= 3.5:
        severity = "severe"
    elif abs_z >= 3.0:
        severity = "moderate"
    elif abs_z >= 2.0:
        severity = "mild"

    direction = "normal"
    if is_anomaly:
        direction = "above" if z_score > 0 else "below"

    return {
        "metric": metric,
        "date": date,
        "date_value": round(date_value, 4),
        "baseline_mean": round(mean, 4),
        "baseline_stddev": round(stddev, 4),
        "z_score": round(z_score, 4),
        "is_anomaly": is_anomaly,
        "anomaly_direction": direction,
        "severity": severity,
    }


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="sse", host=_HOST, port=_PORT)

"""Marketing MCP Server — 4 read tools + 2 write tools.

Tools
-----
- get_campaign_status       campaigns + latest daily metrics
- get_campaign_performance  aggregated CDM metrics per campaign/channel
- get_missed_promotions     orders with no discount during active campaigns
- get_channel_performance   CDM metrics grouped by channel
- pause_campaign            UPDATE campaigns.status  (WRITE)
- apply_discount            INSERT discount_applications  (WRITE)

Run this server::

    python -m mcp_servers.marketing.server
"""

from __future__ import annotations

import os

import psycopg2.extras
from dotenv import load_dotenv
from fastmcp import FastMCP

from mcp_servers.db import db_connection, execute_query, safe_date

load_dotenv()

mcp = FastMCP("marketing-mcp")

_HOST = os.environ.get("MCP_MARKETING_HOST", "localhost")
_PORT = int(os.environ.get("MCP_MARKETING_PORT", "5012"))


# ─────────────────────────────────────────────────────────────────────────────
# tools
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def get_campaign_status(
    start_date: str,
    end_date: str | None = None,
    status_filter: str = "all",
) -> dict:
    """Get status of all campaigns overlapping a date range."""
    start_date = safe_date(start_date)
    end = safe_date(end_date) or start_date

    status_clause = ""
    params: dict = {"start": start_date, "end": end}

    if status_filter != "all":
        status_clause = "AND c.status = %(status_filter)s"
        params["status_filter"] = status_filter

    sql = f"""
        SELECT
            c.campaign_id,
            c.name,
            c.channel,
            c.status,
            c.start_date::text,
            c.end_date::text,
            c.daily_budget,
            -- latest day's metrics within the window
            ROUND(AVG(cdm.roas)::numeric, 4)              AS avg_roas,
            ROUND(AVG(cdm.ctr)::numeric, 4)               AS avg_ctr,
            SUM(cdm.clicks)                               AS total_clicks,
            SUM(cdm.impressions)                          AS total_impressions,
            ROUND(SUM(cdm.spend)::numeric, 2)             AS total_spend,
            ROUND(SUM(cdm.attributed_revenue)::numeric, 2) AS total_attributed_revenue
        FROM campaigns c
        LEFT JOIN campaign_daily_metrics cdm
               ON cdm.campaign_id = c.campaign_id
              AND cdm.date BETWEEN %(start)s AND %(end)s
        WHERE (c.start_date <= %(end)s AND c.end_date >= %(start)s)
          {status_clause}
        GROUP BY c.campaign_id, c.name, c.channel, c.status,
                 c.start_date, c.end_date, c.daily_budget
        ORDER BY total_attributed_revenue DESC NULLS LAST
    """
    rows = execute_query(sql, params)
    return {
        "period": {"start": start_date, "end": end},
        "status_filter": status_filter,
        "campaigns": [dict(r) for r in rows],
        "total_campaigns": len(rows),
    }


@mcp.tool()
def get_campaign_performance(
    start_date: str,
    end_date: str | None = None,
    campaign_id: str | None = None,
    channel: str | None = None,
) -> dict:
    """Get detailed performance metrics for campaigns in a date range."""
    start_date = safe_date(start_date)
    end = safe_date(end_date) or start_date

    filters = ["cdm.date BETWEEN %(start)s AND %(end)s"]
    params: dict = {"start": start_date, "end": end}

    if campaign_id:
        filters.append("cdm.campaign_id = %(cid)s")
        params["cid"] = campaign_id
    if channel:
        filters.append("c.channel = %(channel)s")
        params["channel"] = channel

    where = " AND ".join(filters)

    sql = f"""
        SELECT
            cdm.campaign_id,
            c.name                                          AS campaign_name,
            c.channel,
            c.status,
            COUNT(DISTINCT cdm.date)                        AS days_active,
            SUM(cdm.impressions)                            AS total_impressions,
            SUM(cdm.clicks)                                 AS total_clicks,
            ROUND(AVG(cdm.ctr)::numeric, 4)                 AS avg_ctr,
            ROUND(SUM(cdm.spend)::numeric, 2)               AS total_spend,
            ROUND(SUM(cdm.attributed_revenue)::numeric, 2)  AS total_attributed_revenue,
            ROUND(AVG(cdm.roas)::numeric, 4)                AS avg_roas,
            ROUND(
                CASE WHEN SUM(cdm.clicks) > 0
                THEN SUM(cdm.attributed_revenue) / SUM(cdm.clicks) ELSE NULL END
            ::numeric, 4)                                   AS revenue_per_click
        FROM campaign_daily_metrics cdm
        JOIN campaigns c ON c.campaign_id = cdm.campaign_id
        WHERE {where}
        GROUP BY cdm.campaign_id, c.name, c.channel, c.status
        ORDER BY total_attributed_revenue DESC
    """
    rows = execute_query(sql, params)
    return {
        "period": {"start": start_date, "end": end},
        "campaigns": [dict(r) for r in rows],
    }


@mcp.tool()
def get_missed_promotions(
    start_date: str,
    end_date: str | None = None,
) -> dict:
    """Find orders placed during active campaigns that received no discount."""
    start_date = safe_date(start_date)
    end = safe_date(end_date) or start_date

    sql = """
        SELECT
            c.campaign_id,
            c.name                                              AS campaign_name,
            c.channel,
            COUNT(DISTINCT o.order_id)                         AS orders_with_no_discount,
            ROUND(SUM(o.final_value)::numeric, 2)              AS missed_revenue_opportunity,
            ROUND(AVG(o.final_value)::numeric, 2)              AS avg_order_value
        FROM campaigns c
        JOIN orders o ON o.created_date::date BETWEEN c.start_date AND c.end_date
                     AND o.discount_amount = 0
        WHERE c.start_date <= %(end)s
          AND c.end_date   >= %(start)s
          AND c.status IN ('active', 'completed')
          AND o.created_date BETWEEN %(start)s AND %(end)s
        GROUP BY c.campaign_id, c.name, c.channel
        HAVING COUNT(DISTINCT o.order_id) > 0
        ORDER BY missed_revenue_opportunity DESC
    """
    rows = execute_query(sql, {"start": start_date, "end": end})
    return {
        "period": {"start": start_date, "end": end},
        "missed_promotions": [dict(r) for r in rows],
        "total_campaigns_with_misses": len(rows),
    }


@mcp.tool()
def get_channel_performance(
    start_date: str,
    end_date: str | None = None,
) -> dict:
    """Compare performance across marketing channels for a date range."""
    start_date = safe_date(start_date)
    end = safe_date(end_date) or start_date

    sql = """
        SELECT
            c.channel,
            COUNT(DISTINCT cdm.campaign_id)                 AS campaign_count,
            SUM(cdm.impressions)                            AS total_impressions,
            SUM(cdm.clicks)                                 AS total_clicks,
            ROUND(AVG(cdm.ctr)::numeric, 4)                 AS avg_ctr,
            ROUND(SUM(cdm.spend)::numeric, 2)               AS total_spend,
            ROUND(SUM(cdm.attributed_revenue)::numeric, 2)  AS total_attributed_revenue,
            ROUND(AVG(cdm.roas)::numeric, 4)                AS avg_roas,
            ROUND(
                CASE WHEN SUM(cdm.spend) > 0
                THEN SUM(cdm.attributed_revenue) / SUM(cdm.spend) ELSE NULL END
            ::numeric, 4)                                   AS overall_roas
        FROM campaign_daily_metrics cdm
        JOIN campaigns c ON c.campaign_id = cdm.campaign_id
        WHERE cdm.date BETWEEN %(start)s AND %(end)s
        GROUP BY c.channel
        ORDER BY total_attributed_revenue DESC
    """
    rows = execute_query(sql, {"start": start_date, "end": end})
    return {
        "period": {"start": start_date, "end": end},
        "channels": [dict(r) for r in rows],
    }


@mcp.tool()
def pause_campaign(
    campaign_id: str,
    action: str,
) -> dict:
    """Pause or reactivate a campaign.  REQUIRES APPROVAL.

    *action* must be 'pause' or 'reactivate'.
    """
    valid_actions = {"pause", "reactivate"}
    if action not in valid_actions:
        return {"error": f"Invalid action '{action}'. Choose from: {sorted(valid_actions)}"}

    # Verify campaign exists
    campaign_rows = execute_query(
        "SELECT campaign_id, name, status FROM campaigns WHERE campaign_id = %(cid)s",
        {"cid": campaign_id},
    )
    if not campaign_rows:
        return {"error": f"Campaign '{campaign_id}' not found"}

    current = campaign_rows[0]
    new_status = "paused" if action == "pause" else "active"

    if current["status"] == new_status:
        return {
            "success": False,
            "message": f"Campaign is already '{new_status}'",
            "campaign_id": campaign_id,
            "status": new_status,
        }

    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE campaigns SET status = %(new_status)s WHERE campaign_id = %(cid)s",
                {"new_status": new_status, "cid": campaign_id},
            )
        conn.commit()

    return {
        "success": True,
        "campaign_id": campaign_id,
        "campaign_name": current["name"],
        "previous_status": current["status"],
        "new_status": new_status,
        "action": action,
    }


@mcp.tool()
def apply_discount(
    discount_percent: float,
    duration_days: int,
    product_ids: list[str] | None = None,
    category: str | None = None,
    reason: str | None = None,
) -> dict:
    """Apply a temporary discount to specified products.  REQUIRES APPROVAL.

    Provide either product_ids (list of specific IDs) OR category (e.g. "Electronics")
    to target an entire product category. At least one must be supplied.
    discount_percent must be between 1 and 50.
    duration_days must be between 1 and 30.
    """
    if not (1 <= discount_percent <= 50):
        return {"error": "discount_percent must be between 1 and 50"}
    if not (1 <= duration_days <= 30):
        return {"error": "duration_days must be between 1 and 30"}
    if not product_ids and not category:
        return {"error": "Provide product_ids or category (e.g. 'Electronics')"}

    # Resolve product list from category if no explicit IDs given
    if category and not product_ids:
        rows = execute_query(
            "SELECT product_id, name FROM products WHERE category ILIKE %(cat)s AND is_active = true",
            {"cat": category},
        )
        if not rows:
            return {"error": f"No active products found for category '{category}'"}
        existing = rows
    else:
        existing = execute_query(
            "SELECT product_id, name FROM products WHERE product_id = ANY(%(pids)s)",
            {"pids": product_ids},
        )
        existing_ids = {r["product_id"] for r in existing}
        missing = [pid for pid in (product_ids or []) if pid not in existing_ids]
        if missing:
            return {"error": f"Unknown product_ids: {missing}"}

    inserted: list[dict] = []

    with db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            for row in existing:
                cur.execute(
                    """
                    INSERT INTO discount_applications
                        (product_id, discount_percent, duration_days, reason, applied_at, expires_at, status)
                    VALUES
                        (%(pid)s, %(pct)s, %(days)s, %(reason)s, NOW(),
                         NOW() + (%(days)s || ' days')::interval, 'active')
                    RETURNING application_id::text, expires_at::text
                    """,
                    {
                        "pid": row["product_id"],
                        "pct": discount_percent,
                        "days": duration_days,
                        "reason": reason or "",
                    },
                )
                result = dict(cur.fetchone())
                inserted.append({
                    "product_id": row["product_id"],
                    "product_name": row["name"],
                    "application_id": result["application_id"],
                    "expires_at": result["expires_at"],
                })
        conn.commit()

    return {
        "success": True,
        "discount_percent": discount_percent,
        "duration_days": duration_days,
        "category": category,
        "reason": reason,
        "applied_to": inserted,
        "total_products": len(inserted),
    }


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="sse", host=_HOST, port=_PORT)

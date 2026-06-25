"""Inventory MCP Server — 4 read tools + 1 write tool.

Tools
-----
- get_stock_levels              latest stock snapshot per product/region
- get_stockout_events           products with stockout_hours > threshold
- get_near_stockout             products with < threshold_days of stock left
- get_product_availability_impact  lost demand analysis
- restock_product               INSERT into restock_requests  (WRITE)

Run this server::

    python -m mcp_servers.inventory.server
"""

from __future__ import annotations

import os
import re

from dotenv import load_dotenv
from fastmcp import FastMCP

from mcp_servers.db import execute_query, safe_date

load_dotenv()

mcp = FastMCP("inventory-mcp")

_HOST = os.environ.get("MCP_INVENTORY_HOST", "localhost")
_PORT = int(os.environ.get("MCP_INVENTORY_PORT", "5011"))


# ─────────────────────────────────────────────────────────────────────────────
# tools
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def resolve_products(text: str, limit: int = 5) -> dict:
    """Resolve product IDs or product names mentioned in free text.

    This read-only helper is intended for action planning.  It first detects
    explicit product IDs such as ``PROD-063`` or ``PROD -063``.  If no IDs are
    present, it looks for product names contained in the text.
    """
    cleaned = " ".join((text or "").split())
    limit = max(1, min(int(limit or 5), 20))

    product_ids = []
    seen = set()
    for match in re.finditer(r"\bPROD\s*-?\s*(\d{1,4})\b", cleaned, flags=re.IGNORECASE):
        pid = f"PROD-{int(match.group(1)):03d}"
        if pid not in seen:
            seen.add(pid)
            product_ids.append(pid)

    if product_ids:
        rows = execute_query(
            """
            SELECT product_id, name AS product_name, category
            FROM products
            WHERE product_id = ANY(%(pids)s)
            ORDER BY product_id
            """,
            {"pids": product_ids},
        )
        return {
            "query": text,
            "matches": [dict(r) for r in rows],
            "match_count": len(rows),
            "ambiguous": False,
            "resolution_method": "product_id",
        }

    rows = execute_query(
        """
        SELECT product_id, name AS product_name, category
        FROM products
        WHERE %(text)s ILIKE ('%%' || name || '%%')
        ORDER BY LENGTH(name) DESC, product_id
        LIMIT %(limit)s
        """,
        {"text": cleaned, "limit": limit},
    )
    return {
        "query": text,
        "matches": [dict(r) for r in rows],
        "match_count": len(rows),
        "ambiguous": len(rows) > 1,
        "resolution_method": "product_name",
    }


@mcp.tool()
def get_stock_levels(
    product_ids: list[str] | None = None,
    region: str | None = None,
    category: str | None = None,
    date: str | None = None,
    include_zero_stock: bool = False,
) -> dict:
    """Get current stock levels for products.

    If *date* is omitted the latest available snapshot is used.
    Use *category* to filter by product category (e.g. 'Electronics', 'Clothing').
    """
    date = safe_date(date)
    # Resolve the snapshot date
    snap_date: str | None
    if date:
        snap_date = date
    else:
        snap_rows = execute_query("SELECT MAX(date) AS d FROM inventory_daily")
        snap_date = str(snap_rows[0]["d"]) if snap_rows and snap_rows[0]["d"] else None
        if not snap_date:
            return {"error": "No inventory data found"}

    filters = ["id.date = %(snap_date)s"]
    params: dict = {"snap_date": snap_date}

    if region:
        filters.append("id.region = %(region)s")
        params["region"] = region
    if product_ids:
        filters.append("id.product_id = ANY(%(pids)s)")
        params["pids"] = product_ids
    if category:
        filters.append("p.category ILIKE %(category)s")
        params["category"] = f"%{category}%"
    if not include_zero_stock:
        filters.append("id.closing_stock > 0")

    where = " AND ".join(filters)

    sql = f"""
        SELECT
            id.product_id,
            p.name          AS product_name,
            p.category,
            id.region,
            id.closing_stock,
            id.stockout_hours
        FROM inventory_daily id
        JOIN products p ON p.product_id = id.product_id
        WHERE {where}
        ORDER BY id.closing_stock ASC
    """
    rows = execute_query(sql, params)
    return {
        "snapshot_date": snap_date,
        "stock_levels": [dict(r) for r in rows],
        "total_products": len(rows),
    }


@mcp.tool()
def get_stockout_events(
    start_date: str,
    end_date: str | None = None,
    min_stockout_hours: float = 1.0,
) -> dict:
    """Get products that had stockout events in a date range."""
    start_date = safe_date(start_date)
    end = safe_date(end_date) or start_date

    sql = """
        SELECT
            id.product_id,
            p.name                                           AS product_name,
            id.region,
            id.date::text                                    AS date,
            id.stockout_hours,
            id.lost_demand,
            ROUND((p.price * id.lost_demand)::numeric, 2)   AS lost_revenue_estimate
        FROM inventory_daily id
        JOIN products p ON p.product_id = id.product_id
        WHERE id.date BETWEEN %(start)s AND %(end)s
          AND id.stockout_hours >= %(min_hours)s
        ORDER BY id.stockout_hours DESC
    """
    params = {"start": start_date, "end": end, "min_hours": min_stockout_hours}
    rows = execute_query(sql, params)

    total_lost_revenue = sum(float(r.get("lost_revenue_estimate") or 0) for r in rows)

    return {
        "period": {"start": start_date, "end": end},
        "stockout_events": [dict(r) for r in rows],
        "total_lost_revenue_estimate": round(total_lost_revenue, 2),
    }


@mcp.tool()
def get_near_stockout(
    threshold_days: int = 3,
    region: str | None = None,
) -> dict:
    """Get products that are near stockout threshold.

    A product/region is 'near stockout' when its current closing stock is
    less than *threshold_days* x average daily demand calculated over the
    last 30 days.
    """
    # Latest snapshot date
    snap_rows = execute_query("SELECT MAX(date) AS d FROM inventory_daily")
    snap_date = str(snap_rows[0]["d"]) if snap_rows and snap_rows[0]["d"] else None
    if not snap_date:
        return {"error": "No inventory data found"}

    region_filter = "AND id.region = %(region)s" if region else ""
    params: dict = {
        "snap_date": snap_date,
        "threshold_days": threshold_days,
    }
    if region:
        params["region"] = region

    sql = f"""
        WITH avg_demand AS (
            SELECT
                product_id,
                region,
                AVG(units_sold)::numeric AS avg_daily_demand
            FROM inventory_daily
            WHERE date >= (%(snap_date)s::date - 30)
            GROUP BY product_id, region
        ),
        latest AS (
            SELECT
                id.product_id,
                id.region,
                id.closing_stock
            FROM inventory_daily id
            WHERE id.date = %(snap_date)s
              {region_filter}
        )
        SELECT
            l.product_id,
            p.name                              AS product_name,
            p.category,
            l.region,
            l.closing_stock,
            ROUND(ad.avg_daily_demand, 2)       AS avg_daily_demand,
            ROUND(
                CASE WHEN ad.avg_daily_demand > 0
                THEN l.closing_stock / ad.avg_daily_demand
                ELSE NULL END,
                1
            )                                   AS days_of_stock_remaining
        FROM latest l
        JOIN products p  ON p.product_id  = l.product_id
        JOIN avg_demand ad ON ad.product_id = l.product_id AND ad.region = l.region
        WHERE ad.avg_daily_demand > 0
          AND l.closing_stock < ad.avg_daily_demand * %(threshold_days)s
        ORDER BY days_of_stock_remaining ASC NULLS LAST
    """
    rows = execute_query(sql, params)
    return {
        "snapshot_date": snap_date,
        "threshold_days": threshold_days,
        "near_stockout_products": [dict(r) for r in rows],
        "total_at_risk": len(rows),
    }


@mcp.tool()
def get_product_availability_impact(
    start_date: str,
    end_date: str | None = None,
    product_ids: list[str] | None = None,
) -> dict:
    """Analyse the revenue impact of stock availability issues."""
    start_date = safe_date(start_date)
    end = safe_date(end_date) or start_date

    filters = ["id.date BETWEEN %(start)s AND %(end)s"]
    params: dict = {"start": start_date, "end": end}

    if product_ids:
        filters.append("id.product_id = ANY(%(pids)s)")
        params["pids"] = product_ids

    where = " AND ".join(filters)

    sql = f"""
        SELECT
            id.product_id,
            p.name                                          AS product_name,
            p.category,
            SUM(id.lost_demand)                             AS total_lost_units,
            SUM(id.stockout_hours)                          AS total_stockout_hours,
            COUNT(CASE WHEN id.stockout_hours > 0 THEN 1 END) AS stockout_days,
            ROUND(SUM(id.lost_demand * p.price)::numeric, 2) AS estimated_lost_revenue
        FROM inventory_daily id
        JOIN products p ON p.product_id = id.product_id
        WHERE {where}
        GROUP BY id.product_id, p.name, p.category
        HAVING SUM(id.lost_demand) > 0
        ORDER BY estimated_lost_revenue DESC
    """
    rows = execute_query(sql, params)

    total_lost = sum(float(r.get("estimated_lost_revenue") or 0) for r in rows)

    return {
        "period": {"start": start_date, "end": end},
        "products": [dict(r) for r in rows],
        "total_estimated_lost_revenue": round(total_lost, 2),
    }


@mcp.tool()
def restock_product(
    product_id: str,
    region: str,
    quantity: int,
    priority: str = "normal",
) -> dict:
    """Create a restock request for a product in a region.  REQUIRES APPROVAL.

    Valid priority values: low, normal, high, urgent.
    """
    valid_priorities = {"low", "normal", "high", "urgent"}
    if priority not in valid_priorities:
        return {"error": f"Invalid priority '{priority}'. Choose from: {sorted(valid_priorities)}"}

    if quantity <= 0:
        return {"error": "quantity must be a positive integer"}

    # Verify product exists
    product_rows = execute_query(
        "SELECT product_id, name FROM products WHERE product_id = %(pid)s",
        {"pid": product_id},
    )
    if not product_rows:
        return {"error": f"Product '{product_id}' not found"}

    import psycopg2.extras

    from mcp_servers.db import db_connection

    with db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 1. Find the latest inventory snapshot date for this product/region
            cur.execute(
                """
                SELECT MAX(date) AS snap_date
                FROM inventory_daily
                WHERE product_id = %(pid)s AND region = %(region)s
                """,
                {"pid": product_id, "region": region},
            )
            snap_row = cur.fetchone()
            snap_date = snap_row["snap_date"] if snap_row else None

            # 2. Record the restock request as immediately fulfilled
            cur.execute(
                """
                INSERT INTO restock_requests
                    (product_id, region, quantity, priority, status, requested_at, fulfilled_at)
                VALUES
                    (%(product_id)s, %(region)s, %(quantity)s, %(priority)s,
                     'fulfilled', NOW(), NOW())
                RETURNING request_id::text, requested_at::text
                """,
                {
                    "product_id": product_id,
                    "region": region,
                    "quantity": quantity,
                    "priority": priority,
                },
            )
            result = dict(cur.fetchone())

            # 3. Apply the stock increase to inventory_daily on the latest snapshot row
            inventory_updated = False
            if snap_date:
                cur.execute(
                    """
                    UPDATE inventory_daily
                    SET closing_stock  = closing_stock + %(qty)s,
                        units_received = units_received + %(qty)s
                    WHERE product_id = %(pid)s
                      AND region     = %(region)s
                      AND date       = %(snap_date)s
                    """,
                    {
                        "qty": quantity,
                        "pid": product_id,
                        "region": region,
                        "snap_date": snap_date,
                    },
                )
                inventory_updated = cur.rowcount > 0

        conn.commit()

    return {
        "success": True,
        "request_id": result.get("request_id"),
        "product_id": product_id,
        "product_name": product_rows[0]["name"],
        "region": region,
        "quantity": quantity,
        "priority": priority,
        "status": "fulfilled",
        "inventory_updated": inventory_updated,
        "snapshot_date_updated": str(snap_date) if snap_date else None,
        "requested_at": str(result.get("requested_at", "")),
    }


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="sse", host=_HOST, port=_PORT)

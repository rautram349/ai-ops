"""Support MCP Server — 4 read tools + 1 write tool.

Tools
-----
- get_complaint_summary     support_tickets grouped by category / severity
- get_issue_clusters        theme-based clustering of tickets
- get_refund_return_summary returns table aggregated
- get_review_sentiment      reviews grouped by sentiment / rating
- create_support_ticket     INSERT into support_tickets  (WRITE)

Run this server::

    python -m mcp_servers.support.server
"""

from __future__ import annotations

import psycopg2.extras
from fastmcp import FastMCP

from mcp_servers.config import MCP_SUPPORT_HOST as _HOST, MCP_SUPPORT_PORT as _PORT
from mcp_servers.db import db_connection, execute_query, safe_date

mcp = FastMCP("support-mcp")

_VALID_CATEGORIES = {"shipping", "product_quality", "payment", "availability", "other"}
_VALID_SEVERITIES = {"low", "medium", "high", "critical"}


# ─────────────────────────────────────────────────────────────────────────────
# tools
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def get_complaint_summary(
    start_date: str,
    end_date: str | None = None,
    category: str | None = None,
    severity: str | None = None,
) -> dict:
    """Get summary of customer complaints for a date range."""
    start_date = safe_date(start_date)
    end = safe_date(end_date) or start_date

    filters = ["st.created_date BETWEEN %(start)s AND %(end)s"]
    params: dict = {"start": start_date, "end": end}

    if category:
        filters.append("st.category = %(category)s")
        params["category"] = category
    if severity:
        filters.append("st.severity = %(severity)s")
        params["severity"] = severity

    where = " AND ".join(filters)

    # overall count
    total_sql = f"SELECT COUNT(*) AS n FROM support_tickets st WHERE {where}"
    total_rows = execute_query(total_sql, params)
    total_tickets = int((total_rows[0]["n"]) if total_rows else 0)

    # by category
    cat_sql = f"""
        SELECT category, COUNT(*) AS ticket_count
        FROM support_tickets st
        WHERE {where}
        GROUP BY category
        ORDER BY ticket_count DESC
    """
    by_category = [dict(r) for r in execute_query(cat_sql, params)]

    # by severity
    sev_sql = f"""
        SELECT severity, COUNT(*) AS ticket_count
        FROM support_tickets st
        WHERE {where}
        GROUP BY severity
        ORDER BY ticket_count DESC
    """
    by_severity = [dict(r) for r in execute_query(sev_sql, params)]

    # period comparison — same number of days immediately before start_date
    days_in_period_sql = """
        SELECT (%(end)s::date - %(start)s::date + 1) AS days
    """
    days_row = execute_query(days_in_period_sql, {"start": start_date, "end": end})
    n_days = int(days_row[0]["days"]) if days_row else 1

    prev_sql = """
        SELECT COUNT(*) AS n,
               COUNT(*) / NULLIF(%(days)s, 0)::numeric AS avg_per_day
        FROM support_tickets
        WHERE created_date BETWEEN (%(start)s::date - %(days)s) AND (%(start)s::date - 1)
    """
    prev_rows = execute_query(prev_sql, {"start": start_date, "days": n_days})
    prev_avg = float((prev_rows[0]["avg_per_day"]) if prev_rows and prev_rows[0]["avg_per_day"] else 0)
    current_avg = total_tickets / n_days if n_days else 0

    change_pct = round((current_avg - prev_avg) / prev_avg * 100, 2) if prev_avg else None
    is_spike = bool(change_pct and change_pct > 30)

    return {
        "period": {"start": start_date, "end": end},
        "total_tickets": total_tickets,
        "by_category": by_category,
        "by_severity": by_severity,
        "period_comparison": {
            "current_avg_per_day": round(current_avg, 2),
            "previous_period_avg": round(prev_avg, 2),
            "change_pct": change_pct,
            "is_spike": is_spike,
        },
    }


@mcp.tool()
def get_issue_clusters(
    start_date: str,
    end_date: str | None = None,
    min_cluster_size: int = 3,
) -> dict:
    """Identify clusters of similar issues from support tickets grouped by theme."""
    start_date = safe_date(start_date)
    end = safe_date(end_date) or start_date

    sql = """
        SELECT
            st.category                                       AS theme,
            COUNT(*)                                          AS ticket_count,
            array_agg(DISTINCT st.category)                  AS categories,
            array_agg(DISTINCT st.severity)                  AS severities,
            array_agg(st.subject ORDER BY st.created_date DESC) FILTER
                (WHERE st.subject IS NOT NULL)               AS sample_subjects_raw,
            -- severity counts
            COUNT(*) FILTER (WHERE st.severity = 'critical') AS critical_count,
            COUNT(*) FILTER (WHERE st.severity = 'high')     AS high_count,
            COUNT(*) FILTER (WHERE st.severity = 'medium')   AS medium_count,
            COUNT(*) FILTER (WHERE st.severity = 'low')      AS low_count
        FROM support_tickets st
        WHERE st.created_date BETWEEN %(start)s AND %(end)s
        GROUP BY st.category
        HAVING COUNT(*) >= %(min_size)s
        ORDER BY ticket_count DESC
    """
    rows = execute_query(sql, {"start": start_date, "end": end, "min_size": min_cluster_size})

    clusters = []
    for r in rows:
        raw_subjects = r.get("sample_subjects_raw") or []
        sample_subjects = [str(s) for s in raw_subjects[:5]]
        clusters.append({
            "theme": r["theme"],
            "ticket_count": r["ticket_count"],
            "categories": list(r.get("categories") or []),
            "sample_subjects": sample_subjects,
            "severity_distribution": {
                "critical": int(r["critical_count"] or 0),
                "high":     int(r["high_count"] or 0),
                "medium":   int(r["medium_count"] or 0),
                "low":      int(r["low_count"] or 0),
            },
        })

    return {
        "period": {"start": start_date, "end": end},
        "clusters": clusters,
        "total_clusters": len(clusters),
    }


@mcp.tool()
def get_refund_return_summary(
    start_date: str,
    end_date: str | None = None,
) -> dict:
    """Get summary of refunds and returns for a date range."""
    start_date = safe_date(start_date)
    end = safe_date(end_date) or start_date

    sql = """
        SELECT
            COUNT(*)                                  AS total_returns,
            ROUND(SUM(refund_amount)::numeric, 2)     AS total_refund_amount,
            ROUND(AVG(refund_amount)::numeric, 2)     AS avg_refund_amount
        FROM returns_refunds
        WHERE requested_date BETWEEN %(start)s AND %(end)s
    """
    totals_rows = execute_query(sql, {"start": start_date, "end": end})
    totals = dict(totals_rows[0]) if totals_rows else {}

    by_reason_sql = """
        SELECT
            reason,
            COUNT(*) AS count,
            ROUND(SUM(refund_amount)::numeric, 2) AS total_refund
        FROM returns_refunds
        WHERE requested_date BETWEEN %(start)s AND %(end)s
        GROUP BY reason
        ORDER BY count DESC
    """
    by_reason = [dict(r) for r in execute_query(by_reason_sql, {"start": start_date, "end": end})]

    by_status_sql = """
        SELECT
            status,
            COUNT(*) AS count
        FROM returns_refunds
        WHERE requested_date BETWEEN %(start)s AND %(end)s
        GROUP BY status
        ORDER BY count DESC
    """
    by_status = [dict(r) for r in execute_query(by_status_sql, {"start": start_date, "end": end})]

    return {
        "period": {"start": start_date, "end": end},
        "total_returns": int(totals.get("total_returns") or 0),
        "total_refund_amount": float(totals.get("total_refund_amount") or 0),
        "avg_refund_amount": float(totals.get("avg_refund_amount") or 0),
        "by_reason": by_reason,
        "by_status": by_status,
    }


@mcp.tool()
def get_review_sentiment(
    start_date: str,
    end_date: str | None = None,
    product_ids: list[str] | None = None,
    category: str | None = None,
) -> dict:
    """Get review sentiment analysis for a date range."""
    start_date = safe_date(start_date)
    end = safe_date(end_date) or start_date

    filters = ["r.created_date BETWEEN %(start)s AND %(end)s"]
    params: dict = {"start": start_date, "end": end}

    if product_ids:
        filters.append("r.product_id = ANY(%(pids)s)")
        params["pids"] = product_ids
    if category:
        filters.append("p.category ILIKE %(category)s")
        params["category"] = category

    join = "JOIN products p ON p.product_id = r.product_id" if category or product_ids else ""
    where = " AND ".join(filters)

    sql = f"""
        SELECT
            r.sentiment,
            COUNT(*)                        AS review_count,
            ROUND(AVG(r.rating)::numeric, 2) AS avg_rating
        FROM reviews r
        {join}
        WHERE {where}
        GROUP BY r.sentiment
        ORDER BY review_count DESC
    """
    by_sentiment = [dict(r) for r in execute_query(sql, params)]

    overall_sql = f"""
        SELECT
            COUNT(*)                        AS total_reviews,
            ROUND(AVG(r.rating)::numeric, 2) AS overall_avg_rating
        FROM reviews r
        {join}
        WHERE {where}
    """
    overall_rows = execute_query(overall_sql, params)
    overall = dict(overall_rows[0]) if overall_rows else {}

    # top themes by sentiment
    theme_sql = f"""
        SELECT
            r.theme,
            r.sentiment,
            COUNT(*) AS count
        FROM reviews r
        {join}
        WHERE {where}
          AND r.theme IS NOT NULL
        GROUP BY r.theme, r.sentiment
        ORDER BY count DESC
        LIMIT 15
    """
    top_themes = [dict(r) for r in execute_query(theme_sql, params)]

    return {
        "period": {"start": start_date, "end": end},
        "total_reviews": int(overall.get("total_reviews") or 0),
        "overall_avg_rating": float(overall.get("overall_avg_rating") or 0),
        "by_sentiment": by_sentiment,
        "top_themes": top_themes,
    }


@mcp.tool()
def create_support_ticket(
    category: str,
    severity: str,
    subject: str,
    description: str,
) -> dict:
    """Create a support ticket for an identified issue.  REQUIRES APPROVAL."""
    if category not in _VALID_CATEGORIES:
        return {"error": f"Invalid category '{category}'. Choose from: {sorted(_VALID_CATEGORIES)}"}
    if severity not in _VALID_SEVERITIES:
        return {"error": f"Invalid severity '{severity}'. Choose from: {sorted(_VALID_SEVERITIES)}"}
    if not subject.strip():
        return {"error": "subject must not be empty"}
    if not description.strip():
        return {"error": "description must not be empty"}

    with db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Derive next ticket_id from current MAX (format: TKT-NNNNNN)
            cur.execute("SELECT MAX(ticket_id) FROM support_tickets")
            max_id: str | None = cur.fetchone()["max"]
            if max_id:
                next_num = int(max_id.split("-")[1]) + 1
            else:
                next_num = 1
            ticket_id = f"TKT-{next_num:06d}"

            # Use a system/internal placeholder customer that satisfies the FK
            cur.execute("SELECT customer_id FROM customers ORDER BY customer_id LIMIT 1")
            system_customer_id = cur.fetchone()["customer_id"]

            cur.execute(
                """
                INSERT INTO support_tickets
                    (ticket_id, customer_id, region,
                     category, severity, subject, description,
                     status, created_at, created_date)
                VALUES
                    (%(ticket_id)s, %(customer_id)s, 'all',
                     %(category)s, %(severity)s, %(subject)s, %(description)s,
                     'open', NOW(), NOW()::date)
                RETURNING ticket_id::text, created_date::text
                """,
                {
                    "ticket_id":   ticket_id,
                    "customer_id": system_customer_id,
                    "category":    category,
                    "severity":    severity,
                    "subject":     subject,
                    "description": description,
                },
            )
            result = dict(cur.fetchone())
        conn.commit()

    return {
        "success": True,
        "ticket_id": result["ticket_id"],
        "category": category,
        "severity": severity,
        "subject": subject,
        "status": "open",
        "created_date": result["created_date"],
    }


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="sse", host=_HOST, port=_PORT)

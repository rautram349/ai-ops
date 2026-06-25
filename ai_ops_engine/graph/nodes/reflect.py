"""Graph node — reflect: evaluate evidence quality, optionally reinvestigate."""

from __future__ import annotations

import json

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from ai_ops_engine.graph.domains import DOMAIN_TO_SERVER
from ai_ops_engine.graph.nodes.shared import (
    _days_ago,
    _strip_code_fences,
    _summarise_domain_findings,
    _summarise_tool_results,
    _today,
)
from ai_ops_engine.graph.state import AgentState
from ai_ops_engine.llm import get_llm
from ai_ops_engine.prompts import REFLECT_SYSTEM as _REFLECT_SYSTEM

logger = structlog.get_logger(__name__)

# ── Sanitization constants ────────────────────────────────────────────────────

_VALID_SERVERS: frozenset[str] = frozenset(DOMAIN_TO_SERVER.values())
_DETECT_ANOMALY_TOOL = {"detect_anomaly"}
_COMPARE_SALES_TOOL = {"compare_sales"}
_DATE_ARG_TOOLS = {
    "get_sales_summary",
    "get_revenue_by_product",
    "get_revenue_by_region",
    "get_stockout_events",
    "get_product_availability_impact",
    "get_campaign_status",
    "get_campaign_performance",
    "get_missed_promotions",
    "get_channel_performance",
    "get_issue_clusters",
    "get_refund_return_summary",
}
_DATE_FILTER_TOOLS = {
    "get_complaint_summary",
    "get_review_sentiment",
}
_NO_ARG_TOOLS = {"get_stock_levels", "get_near_stockout"}
_ALL_KNOWN_TOOLS = (
    _DATE_ARG_TOOLS
    | _DATE_FILTER_TOOLS
    | _NO_ARG_TOOLS
    | _DETECT_ANOMALY_TOOL
    | _COMPARE_SALES_TOOL
)


def _sanitize_follow_up_tools(tools: list[dict]) -> list[dict]:
    """Normalize LLM-generated follow-up tool specs."""
    sanitized = []
    for tc in tools:
        server = str(tc.get("server", "")).lower().strip()
        for suffix in (" server", " servers"):
            if server.endswith(suffix):
                server = server[: -len(suffix)].strip()

        tool = str(tc.get("tool", "")).strip()
        args = dict(tc.get("arguments", {}) or {})

        if server not in _VALID_SERVERS or tool not in _ALL_KNOWN_TOOLS:
            logger.warning("reflect_invalid_tool_dropped", server=server, tool=tool)
            continue

        if tool in _DETECT_ANOMALY_TOOL:
            metric = args.get("metric") or "revenue"
            date = args.get("date") or args.get("start_date") or _days_ago(1)
            sanitized.append(
                {
                    "server": server,
                    "tool": tool,
                    "arguments": {"metric": metric, "date": date},
                }
            )
            continue

        if tool in _COMPARE_SALES_TOOL:
            period_b_end = args.get("period_b_end") or _today()
            period_b_start = args.get("period_b_start") or _days_ago(14)
            period_a_end = args.get("period_a_end") or _days_ago(15)
            period_a_start = args.get("period_a_start") or _days_ago(29)
            sanitized.append(
                {
                    "server": server,
                    "tool": tool,
                    "arguments": {
                        "period_a_start": period_a_start,
                        "period_a_end": period_a_end,
                        "period_b_start": period_b_start,
                        "period_b_end": period_b_end,
                    },
                }
            )
            continue

        if tool in _DATE_ARG_TOOLS:
            clean_args = {
                "start_date": args.get("start_date") or _days_ago(30),
                "end_date": args.get("end_date") or _today(),
            }
            sanitized.append({"server": server, "tool": tool, "arguments": clean_args})
            continue

        if tool in _DATE_FILTER_TOOLS:
            clean_args = {
                "start_date": args.get("start_date") or _days_ago(30),
                "end_date": args.get("end_date") or _today(),
            }
            if args.get("category"):
                clean_args["category"] = args["category"]
            if args.get("severity"):
                clean_args["severity"] = args["severity"]
            if args.get("product_ids"):
                clean_args["product_ids"] = args["product_ids"]
            sanitized.append({"server": server, "tool": tool, "arguments": clean_args})
            continue

        if tool in _NO_ARG_TOOLS:
            if tool == "get_stock_levels":
                clean_args = {}
                pids = args.get("product_ids") or (
                    [args["product_id"]] if args.get("product_id") else None
                )
                if pids:
                    clean_args["product_ids"] = pids
                if args.get("region"):
                    clean_args["region"] = args["region"]
                if args.get("date"):
                    clean_args["date"] = args["date"]
            else:
                clean_args = {}
                if args.get("threshold_days"):
                    clean_args["threshold_days"] = args["threshold_days"]
                if args.get("region"):
                    clean_args["region"] = args["region"]
            sanitized.append({"server": server, "tool": tool, "arguments": clean_args})
            continue

        sanitized.append({"server": server, "tool": tool, "arguments": args})
    return sanitized


async def reflect(state: AgentState) -> dict:
    """Evaluate evidence quality and optionally trigger a targeted reinvestigation pass."""
    llm = get_llm()

    iteration = state.get("iteration_count", 0)
    if iteration >= 2:
        logger.info("reflect_max_iterations", iteration=iteration)
        return {
            "reflection_summary": "Maximum investigation iterations reached; proceeding with available data.",
            "reflection_confidence": 0.7,
            "reflection_tool_hints": [],
            "iteration_count": iteration,
        }

    findings_text = _summarise_domain_findings(state.get("domain_findings") or [])
    tool_summary = _summarise_tool_results(state["tool_results"])
    prompt_content = (
        f"User query: {state['user_query']}\n"
        f"Intent: {state['intent']}\n"
        f"Domains investigated: {state.get('domain_plan', [])}\n\n"
        f"Domain findings:\n{findings_text}\n\n"
        f"Raw tool data:\n{tool_summary}"
    )

    response = await llm.ainvoke(
        [
            SystemMessage(content=_REFLECT_SYSTEM),
            HumanMessage(content=prompt_content),
        ]
    )

    try:
        cleaned = _strip_code_fences(
            str(response.content) if hasattr(response, "content") else str(response)
        )
        parsed: dict = json.loads(cleaned)
    except (json.JSONDecodeError, AttributeError):
        parsed = {
            "is_complete": True,
            "confidence": 0.7,
            "summary": "Proceeding with available data.",
            "follow_up_tools": [],
        }

    is_complete: bool = bool(parsed.get("is_complete", True))
    confidence: float = float(parsed.get("confidence", 0.7))
    summary: str = str(parsed.get("summary", ""))
    follow_up: list[dict] = parsed.get("follow_up_tools", []) if not is_complete else []

    follow_up = _sanitize_follow_up_tools(follow_up)
    if not follow_up:
        is_complete = True

    logger.info(
        "reflect",
        is_complete=is_complete,
        confidence=confidence,
        follow_up_count=len(follow_up),
    )

    return {
        "reflection_summary": summary,
        "reflection_confidence": confidence,
        "reflection_tool_hints": follow_up,
        "iteration_count": iteration + 1,
    }

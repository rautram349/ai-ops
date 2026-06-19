"""Shared utilities for domain agents."""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from typing import Any, Callable

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ai_ops_engine.clients.mcp_client import get_mcp_client
from ai_ops_engine.graph.state import AgentState, ToolCallRecord
from ai_ops_engine.llm import get_llm

logger = structlog.get_logger(__name__)


# Cap all date helpers at the last date for which data was generated so that
# queries like "this week" don't fall past the data cutoff and return zero rows.
_DATA_END = date(2026, 4, 13)


def _today() -> str:
    return min(date.today(), _DATA_END).isoformat()


def _days_ago(n: int) -> str:
    ref = min(date.today(), _DATA_END)
    return (ref - timedelta(days=n)).isoformat()


def _strip_code_fences(text: str) -> str:
    """Strip markdown code fences (```json ... ```) from LLM output."""
    text = text.strip()
    m = re.match(r"^```(?:json)?\s*\n?(.*?)```$", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text


async def run_domain_agent(
    *,
    state: AgentState,
    domain: str,
    server: str,
    system_prompt: str,
    default_tools: list[dict],
    node_name: str,
    tool_sanitizer: "Callable[[list[dict], str], list[dict]] | None" = None,
) -> dict:
    """Generic domain-agent runner.

    1. Asks the LLM which tools to call (scoped to this domain only).
    2. Executes those tool calls in parallel via MCP.
    3. Returns partial state with tool_results, domain_findings, state updates.

    On the reinvestigate path (reflection_tool_hints present for this domain),
    skips the LLM planning step and runs only the hinted tools.
    """
    llm = get_llm()
    query = state["user_query"]
    intent = state["intent"]

    # ── Check for reflection reinvestigate hints for this domain ──────────
    hints: list[dict] = [
        h for h in (state.get("reflection_tool_hints") or [])
        if h.get("server") == server
    ]

    if hints:
        tool_calls = hints
        logger.info(f"{node_name}_using_hints", num_hints=len(hints))
    else:
        prompt = system_prompt.replace("{today}", _today())
        response = await llm.ainvoke([
            SystemMessage(content=prompt),
            HumanMessage(content=f"Intent: {intent}\nQuery: {query}"),
        ])
        raw = response.content if hasattr(response, "content") else str(response)
        logger.info(f"{node_name}_raw_response", raw=raw[:500])

        try:
            cleaned = _strip_code_fences(raw)
            tool_calls = json.loads(cleaned)
            if not isinstance(tool_calls, list):
                tool_calls = []
        except (json.JSONDecodeError, AttributeError):
            tool_calls = default_tools

        if not tool_calls:
            tool_calls = default_tools

    # ── Sanitize / enrich tool calls (optional per-agent hook) ───────────
    if tool_sanitizer is not None:
        tool_calls = tool_sanitizer(tool_calls, query)

    # ── Execute tool calls ────────────────────────────────────────────────
    client = get_mcp_client()
    parallel = [
        (tc.get("server", server), tc["tool"], tc.get("arguments", {}))
        for tc in tool_calls
    ]
    raw_results = await client.call_tools_parallel(parallel)
    records: list[ToolCallRecord] = []
    for tc, result in zip(tool_calls, raw_results):
        is_error = isinstance(result, Exception)
        records.append(ToolCallRecord(
            server=tc.get("server", server),
            tool=tc["tool"],
            arguments=tc.get("arguments", {}),
            result=None if is_error else result,
            error=str(result) if is_error else None,
        ))
        if is_error:
            logger.error("tool_call_failed", tool=tc["tool"], error=str(result))

    # Build per-domain finding summary
    finding = {
        "domain": domain,
        "server": server,
        "tools_called": [tc["tool"] for tc in tool_calls],
        "tool_results": [
            {"tool": r["tool"], "result": r["result"], "error": r["error"]}
            for r in records
        ],
    }

    summary = f"[{domain}] Executed {len(records)} tool(s): {', '.join(tc['tool'] for tc in tool_calls)}"

    return {
        "tool_results": records,
        "domain_findings": [finding],
        "messages": [AIMessage(content=f"[{node_name}] {summary}")],
    }

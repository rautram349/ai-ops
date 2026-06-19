"""Graph node — execute: run approved write tool calls."""

from __future__ import annotations

import structlog
from langchain_core.messages import AIMessage

from ai_ops_engine.clients.mcp_client import get_mcp_client
from ai_ops_engine.graph.nodes.shared import _now
from ai_ops_engine.graph.state import AgentState, ToolCallRecord

logger = structlog.get_logger(__name__)


async def execute(state: AgentState) -> dict:
    """Execute approved write tool calls."""
    t0 = _now()
    if not state.get("needs_write") or not state.get("approved"):
        t1 = _now()
        return {
            "messages": [AIMessage(content="[execute] No write actions to execute.")],
        }

    client = get_mcp_client()
    records: list[ToolCallRecord] = []
    for approval in state.get("pending_approvals", []):
        tc_start = _now()
        try:
            result = await client.call_tool(
                approval["server"],
                approval["tool"],
                approval["arguments"],
            )
            tc_end = _now()
            tool_error = result.get("error") if isinstance(result, dict) else None
            is_tool_error = bool(tool_error)
            records.append(ToolCallRecord(
                server=approval["server"],
                tool=approval["tool"],
                arguments=approval["arguments"],
                result=None if is_tool_error else result,
                error=tool_error if is_tool_error else None,
            ))
            if is_tool_error:
                logger.error("write_tool_error_response", tool=approval["tool"], error=tool_error)
            else:
                logger.info("write_tool_executed", tool=approval["tool"])
        except Exception as exc:
            tc_end = _now()
            records.append(ToolCallRecord(
                server=approval["server"],
                tool=approval["tool"],
                arguments=approval["arguments"],
                result=None,
                error=str(exc),
            ))
            logger.error("write_tool_failed", tool=approval["tool"], error=str(exc))

    t1 = _now()
    return {
        "tool_results": records,
        "messages": [AIMessage(content=f"[execute] Ran {len(records)} write action(s).")],
    }

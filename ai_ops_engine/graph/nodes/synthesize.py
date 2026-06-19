"""Graph node — synthesize: merge domain findings into cross-domain analysis."""

from __future__ import annotations

import json

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ai_ops_engine.graph.nodes.shared import _now, _strip_code_fences, _summarise_domain_findings, _summarise_tool_results
from ai_ops_engine.graph.state import AgentState
from ai_ops_engine.llm import get_llm
from ai_ops_engine.prompts import SYNTHESIZE_SYSTEM as _SYNTHESIZE_SYSTEM

logger = structlog.get_logger(__name__)


async def synthesize(state: AgentState) -> dict:
    """Merge findings from all domain agents into a cross-domain analysis."""
    llm = get_llm()

    findings = state.get("domain_findings") or []
    findings_text = _summarise_domain_findings(findings)
    tool_summary = _summarise_tool_results(state["tool_results"])
    memory_matches = state.get("memory_matches") or []
    memory_text = (
        json.dumps(memory_matches, default=str, indent=2)
        if memory_matches
        else "No relevant past incidents found."
    )

    response = await llm.ainvoke([
        SystemMessage(content=_SYNTHESIZE_SYSTEM),
        HumanMessage(content=(
            f"User query: {state['user_query']}\n"
            f"Intent: {state['intent']}\n"
            f"Domains investigated: {state.get('domain_plan', [])}\n\n"
            f"Domain findings:\n{findings_text}\n\n"
            f"Past incident memory:\n{memory_text}\n\n"
            f"Raw tool data:\n{tool_summary}"
        )),
    ])

    try:
        cleaned = _strip_code_fences(response.content if hasattr(response, "content") else str(response))
        parsed: dict = json.loads(cleaned)
    except (json.JSONDecodeError, AttributeError):
        parsed = {
            "cross_domain_summary": "Analysis complete — proceeding with available data.",
            "root_causes": [],
            "coverage_gaps": [],
        }

    logger.info("synthesize", num_root_causes=len(parsed.get("root_causes", [])))

    return {
        "messages": [AIMessage(content=f"[synthesize] {parsed.get('cross_domain_summary', '')[:200]}")],
    }

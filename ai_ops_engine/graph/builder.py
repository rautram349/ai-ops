"""LangGraph StateGraph assembly ? multi-agent architecture."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from ai_ops_engine.agents import (
    inventory_agent,
    marketing_agent,
    memory_agent,
    sales_agent,
    support_agent,
)
from ai_ops_engine.graph.nodes import (
    execute,
    plan,
    plan_domains,
    recall,
    reflect,
    respond,
    route,
    synthesize,
)
from ai_ops_engine.graph.state import AgentState
from ai_ops_engine.prompts import UNKNOWN_SYSTEM as _UNKNOWN_SYSTEM

logger = logging.getLogger(__name__)

_DOMAIN_AGENT_MAP: dict[str, str] = {
    "sales": "sales_agent",
    "inventory": "inventory_agent",
    "marketing": "marketing_agent",
    "support": "support_agent",
}


def _after_route(state: AgentState) -> str:
    """Skip the tool-calling pipeline for unknown / conversational intent."""
    intent = state.get("intent")
    if intent == "irrelevant":
        return "respond_guardrail"
    if intent == "unknown":
        return "respond_unknown"
    if intent == "memory_recall":
        return "recall"
    return "plan_domains"


def _respond_guardrail(state: AgentState) -> dict:
    """Deterministic refusal for prompts outside the AI-ops scope."""
    category = state.get("guardrail_category", "irrelevant")
    summary = (
        "I can’t help with that request because it’s outside the AI-ops operational scope. "
        "I can help investigate sales, inventory, marketing, support, incidents, and approval workflows."
    )
    if category == "prompt_injection":
        summary = (
            "I can’t help with requests to override instructions, reveal hidden prompts, or access secrets. "
            "Ask me about sales, inventory, marketing, support, incidents, or operational actions instead."
        )

    return {
        "response_summary": summary,
        "response_details": {
            "summary": summary,
            "findings": [
                {
                    "title": "Prompt blocked by scope guardrail",
                    "detail": state.get("guardrail_reason", "The prompt is outside the supported AI-ops domain."),
                    "severity": "info",
                }
            ],
            "recommendations": [
                {
                    "action_type": "ask_operational_question",
                    "reason": "Try asking about revenue anomalies, stockouts, campaign performance, support complaints, incidents, or approvals.",
                    "risk_level": "low",
                    "reversible": True,
                }
            ],
            "actions_taken": [],
            "pending_approvals": [],
        },
        "messages": [AIMessage(content=summary)],
    }


async def _respond_unknown(state: AgentState) -> dict:
    """Use LLM to generate a smart, context-aware conversational reply."""
    from ai_ops_engine.llm import get_llm

    llm = get_llm()
    query = state["user_query"]

    _SKIP_PREFIXES = ("[route]", "[diagnose]", "[plan]", "[execute]")
    prior_msgs = [
        m
        for m in state.get("messages", [])
        if isinstance(m, (HumanMessage, AIMessage))
        and not m.content.startswith(_SKIP_PREFIXES)
        and m.content != query
    ]

    llm_messages = (
        [SystemMessage(content=_UNKNOWN_SYSTEM)]
        + prior_msgs[-6:]
        + [HumanMessage(content=query)]
    )

    response = await llm.ainvoke(llm_messages)
    reply = response.content if hasattr(response, "content") else str(response)

    return {
        "response_summary": reply,
        "response_details": {
            "summary": reply,
            "findings": [],
            "recommendations": [],
            "actions_taken": [],
            "pending_approvals": [],
        },
        "messages": [AIMessage(content=reply)],
    }


def _after_reflect(state: AgentState) -> str | list[Send]:
    """Route after reflect: reinvestigate (fan-out to agents) or proceed to plan."""
    hints = state.get("reflection_tool_hints", []) or []
    if hints:
        reinvestigate_domains: set[str] = set()
        server_to_domain = {
            "metrics": "sales",
            "inventory": "inventory",
            "marketing": "marketing",
            "support": "support",
        }
        for hint in hints:
            domain = server_to_domain.get(hint.get("server", ""))
            if domain:
                reinvestigate_domains.add(domain)
        if not reinvestigate_domains:
            reinvestigate_domains = set(state.get("domain_plan", []))

        sends = []
        for domain in reinvestigate_domains:
            agent_name = _DOMAIN_AGENT_MAP.get(domain)
            if agent_name:
                sends.append(Send(agent_name, state))
        return sends if sends else "plan"
    return "plan"


def _after_plan(state: AgentState) -> str:
    """Route after the plan node."""
    if not state.get("needs_write"):
        return "respond"
    if state.get("approved"):
        return "execute"
    return "respond_pending"


def _respond_pending(state: AgentState) -> dict:
    """Synthetic node: inform the user that approvals are pending."""
    approvals = state.get("pending_approvals", [])
    lines = [f"- **{a['tool']}** on *{a['server']}*: {a['reason']}" for a in approvals]
    summary = (
        "The following actions require your approval before they can be executed:\n"
        + "\n".join(lines)
    )
    recommendations = [
        {
            "action_type": a.get("tool", "investigate"),
            "reason": a.get("reason", ""),
            "risk_level": a.get("risk_level", "medium"),
            "reversible": bool(a.get("reversible", True)),
        }
        for a in approvals
    ]
    existing_findings: list = []
    for tr in state.get("tool_results", []):
        if not tr.get("error") and isinstance(tr.get("result"), dict):
            existing_findings.append(
                {
                    "title": f"Data from {tr['tool']}",
                    "detail": str(tr["result"])[:300],
                    "severity": "info",
                    "root_cause": "",
                    "affected_products": [],
                    "affected_regions": [],
                }
            )
    return {
        "response_summary": summary,
        "response_details": {
            "summary": summary,
            "findings": existing_findings,
            "recommendations": recommendations,
            "actions_taken": [],
            "pending_approvals": [dict(a) for a in approvals],
        },
    }


def _dispatch_agents(state: AgentState) -> list[Send]:
    """Fan-out from plan_domains to the relevant domain agents via Send."""
    domains = state.get("domain_plan") or ["sales"]
    sends = [Send("memory_agent", state)]
    for domain in domains:
        agent_name = _DOMAIN_AGENT_MAP.get(domain)
        if agent_name:
            sends.append(Send(agent_name, state))
    return sends


def _build_graph() -> Any:
    builder = StateGraph(AgentState)

    builder.add_node("route", route)
    builder.add_node("recall", recall)
    builder.add_node("plan_domains", plan_domains)
    builder.add_node("memory_agent", memory_agent)
    builder.add_node("sales_agent", sales_agent)
    builder.add_node("inventory_agent", inventory_agent)
    builder.add_node("marketing_agent", marketing_agent)
    builder.add_node("support_agent", support_agent)
    builder.add_node("synthesize", synthesize)
    builder.add_node("reflect", reflect)
    builder.add_node("plan", plan)
    builder.add_node("execute", execute)
    builder.add_node("respond", respond)
    builder.add_node("respond_pending", _respond_pending)
    builder.add_node("respond_unknown", _respond_unknown)
    builder.add_node("respond_guardrail", _respond_guardrail)

    builder.add_edge(START, "route")
    builder.add_conditional_edges(
        "route",
        _after_route,
        {
            "plan_domains": "plan_domains",
            "recall": "recall",
            "respond_unknown": "respond_unknown",
            "respond_guardrail": "respond_guardrail",
        },
    )
    builder.add_edge("recall", "respond")

    builder.add_conditional_edges("plan_domains", _dispatch_agents)

    builder.add_edge("memory_agent", "synthesize")
    builder.add_edge("sales_agent", "synthesize")
    builder.add_edge("inventory_agent", "synthesize")
    builder.add_edge("marketing_agent", "synthesize")
    builder.add_edge("support_agent", "synthesize")

    builder.add_edge("synthesize", "reflect")
    builder.add_conditional_edges("reflect", _after_reflect)

    builder.add_conditional_edges(
        "plan",
        _after_plan,
        {
            "respond": "respond",
            "execute": "execute",
            "respond_pending": "respond_pending",
        },
    )

    builder.add_edge("execute", "respond")
    builder.add_edge("respond", END)
    builder.add_edge("respond_pending", END)
    builder.add_edge("respond_unknown", END)
    builder.add_edge("respond_guardrail", END)

    return builder.compile()


graph = _build_graph()


async def run_graph(
    user_query: str,
    conversation_history: list[dict] | None = None,
    approved: bool = False,
    pending_approvals: list[dict] | None = None,
) -> dict[str, Any]:
    """Run the agent graph for a user query."""
    messages = []
    if conversation_history:
        for msg in conversation_history[-10:]:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["content"]))

    messages.append(HumanMessage(content=user_query))

    initial_state: AgentState = {
        "messages": messages,
        "user_query": user_query,
        "intent": "unknown",
        "tool_results": [],
        "pending_approvals": pending_approvals or [],
        "needs_write": False,
        "approved": approved,
        "response_summary": "",
        "response_details": {},
        "error": None,
        "guardrail_status": "allowed",
        "guardrail_reason": "",
        "guardrail_category": "in_scope",
        "memory_matches": [],
        "domain_plan": [],
        "domain_findings": [],
        "iteration_count": 0,
        "reflection_summary": "",
        "reflection_confidence": 1.0,
        "reflection_tool_hints": [],
    }

    final_state: AgentState = await graph.ainvoke(initial_state)

    return {
        "intent": final_state["intent"],
        "response_summary": final_state["response_summary"],
        "response_details": final_state["response_details"],
        "tool_results": final_state["tool_results"],
        "pending_approvals": final_state.get("pending_approvals", []),
        "needs_write": final_state.get("needs_write", False),
        "approved": final_state.get("approved", False),
        "error": final_state.get("error"),
        "memory_matches": final_state.get("memory_matches", []),
    }


_STREAM_NODE_NAMES: frozenset[str] = frozenset(
    {
        "route",
        "recall",
        "plan_domains",
        "memory_agent",
        "sales_agent",
        "inventory_agent",
        "marketing_agent",
        "support_agent",
        "synthesize",
        "reflect",
        "plan",
        "execute",
        "respond",
        "respond_pending",
        "respond_unknown",
        "respond_guardrail",
    }
)


async def stream_graph_events(
    initial_state: dict[str, Any],
) -> AsyncIterator[dict[str, Any]]:
    """Yield progress events while the graph executes."""
    async for event in graph.astream_events(initial_state, version="v2"):
        kind: str = event["event"]
        name: str = event.get("name", "")
        meta: dict = event.get("metadata", {})

        if kind == "on_chain_start":
            lg_node = meta.get("langgraph_node", "")
            if name in _STREAM_NODE_NAMES and lg_node in _STREAM_NODE_NAMES:
                yield {"type": "node_start", "node": name}

        elif kind == "on_chain_end" and name == "LangGraph":
            output = event.get("data", {}).get("output", {})
            yield {"type": "final", "state": output}

"""LangGraph agent state definition.

``AgentState`` is the single TypedDict that flows through every node of the
graph.  Each node reads from it and returns a *partial* dict — LangGraph
merges these partials automatically using the ``Annotated`` reducers defined
here.

Key design decisions
--------------------
* ``messages`` uses ``add_messages`` so that each node can append without
  having to return the full list.
* All other fields use simple last-write-wins (default reducer).
* ``tool_results`` accumulates across multiple diagnose steps via
  ``operator.add`` so results from parallel tool calls are merged.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, Literal

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import NotRequired, TypedDict


# ── Intent literals ───────────────────────────────────────────────────────────

Intent = Literal[
    "sales_analysis",
    "inventory_check",
    "marketing_performance",
    "support_analysis",
    "multi_domain",
    "memory_recall",
    "irrelevant",
    "unknown",
]

# ── Tool call record ──────────────────────────────────────────────────────────

class ToolCallRecord(TypedDict):
    server: str           # 'metrics' | 'inventory' | 'marketing' | 'support'
    tool: str             # tool name
    arguments: dict[str, Any]
    result: Any           # raw return value from MCP tool
    error: str | None     # non-None if the call failed


# ── Approval request ──────────────────────────────────────────────────────────

class PendingApproval(TypedDict):
    tool: str             # write tool name
    server: str
    arguments: dict[str, Any]
    reason: str           # human-readable explanation for why approval is needed
    risk_level: NotRequired[str]   # 'low' | 'medium' | 'high'
    reversible: NotRequired[bool]  # whether the action can be undone


# ── Main state ────────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    # Conversation history — append-only via add_messages reducer
    messages: Annotated[list[BaseMessage], add_messages]

    # Resolved user intent
    intent: Intent

    # Tool calls executed so far — accumulated across nodes
    tool_results: Annotated[list[ToolCallRecord], operator.add]

    # Write actions needing human approval
    pending_approvals: list[PendingApproval]

    # Whether the planner decided that write actions are required
    needs_write: bool

    # Whether all required approvals have been granted
    approved: bool

    # Final response fields (populated by the respond node)
    response_summary: str
    response_details: dict[str, Any]

    # Pass-through: original user query (set once at graph entry)
    user_query: str

    # Error message if any node fails
    error: str | None

    # Guardrail metadata from route. Empty / allowed for normal in-scope queries.
    guardrail_status: NotRequired[str]
    guardrail_reason: NotRequired[str]
    guardrail_category: NotRequired[str]

    # Past incident matches from memory recall (populated by recall node)
    memory_matches: list[dict[str, Any]]


    # ── Multi-agent domain investigation ───────────────────────────────────
    # Which domains to investigate (set by plan_domains node)
    domain_plan: list[str]

    # Per-domain findings collected by each agent — accumulated via operator.add
    domain_findings: Annotated[list[dict[str, Any]], operator.add]

    # ── Reflection loop fields ─────────────────────────────────────────────
    # How many times the investigation loop has run (0 = first pass, 1 = reinvestigate)
    iteration_count: int

    # LLM's assessment of evidence quality (produced by the reflect node)
    reflection_summary: str

    # 0.0–1.0 evidence-sufficiency score from reflect (injected into respond prompt)
    reflection_confidence: float

    # Targeted follow-up tool list produced by reflect. Non-empty → loop back to
    # diagnose which will skip LLM planning and execute only these tools
    reflection_tool_hints: list[dict[str, Any]]

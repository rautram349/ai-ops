"""Graph node — recall: search incident history for past events."""

from __future__ import annotations

import json

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ai_ops_engine.agents.memory_agent import _serialise_incident
from ai_ops_engine.graph.nodes.shared import _strip_code_fences
from ai_ops_engine.graph.state import AgentState
from ai_ops_engine.llm import get_llm
from ai_ops_engine.prompts import RECALL_KEYWORD_SYSTEM as _RECALL_KEYWORD_SYSTEM
# FIXME: inject via MemoryProvider protocol
from backend.db.connection import AsyncSessionLocal
from backend.db.repositories import IncidentRepository

logger = structlog.get_logger(__name__)


async def recall(state: AgentState) -> dict:
    """Search incident history for past events matching the user query."""
    llm = get_llm()
    query = state["user_query"]

    kw_response = await llm.ainvoke([
        SystemMessage(content=_RECALL_KEYWORD_SYSTEM),
        HumanMessage(content=query),
    ])

    try:
        cleaned = _strip_code_fences(
            str(kw_response.content) if hasattr(kw_response, "content") else str(kw_response)
        )
        keywords: list[str] = json.loads(cleaned)
        if not isinstance(keywords, list):
            keywords = []
    except (json.JSONDecodeError, AttributeError):
        keywords = []

    logger.info("recall_keywords", keywords=keywords, query=query[:80])

    memory_matches: list[dict] = []
    try:
        async with AsyncSessionLocal() as session:
            repo = IncidentRepository(session)
            incidents = await repo.search(keywords, limit=5)
            memory_matches = [_serialise_incident(inc) for inc in incidents]
    except Exception as exc:
        logger.error("recall_db_error", error=str(exc))

    logger.info("recall_matches", count=len(memory_matches))

    return {
        "memory_matches": memory_matches,
        "messages": [AIMessage(content=f"[recall] Found {len(memory_matches)} past incident(s) matching query.")],
    }

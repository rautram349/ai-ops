"""Graph node — recall: search incident history for past events."""

from __future__ import annotations

import json

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ai_ops_engine.graph.nodes.shared import _now, _strip_code_fences
from ai_ops_engine.graph.state import AgentState
from ai_ops_engine.llm import get_llm
from ai_ops_engine.prompts import RECALL_KEYWORD_SYSTEM as _RECALL_KEYWORD_SYSTEM

logger = structlog.get_logger(__name__)


async def recall(state: AgentState) -> dict:
    """Search incident history for past events matching the user query."""
    t0 = _now()
    llm = get_llm()
    query = state["user_query"]

    kw_response = await llm.ainvoke([
        SystemMessage(content=_RECALL_KEYWORD_SYSTEM),
        HumanMessage(content=query),
    ])
    t_kw = _now()

    try:
        cleaned = _strip_code_fences(
            kw_response.content if hasattr(kw_response, "content") else str(kw_response)
        )
        keywords: list[str] = json.loads(cleaned)
        if not isinstance(keywords, list):
            keywords = []
    except (json.JSONDecodeError, AttributeError):
        keywords = []

    logger.info("recall_keywords", keywords=keywords, query=query[:80])

    from backend.db.connection import AsyncSessionLocal
    from backend.db.repositories.approvals import IncidentRepository

    memory_matches: list[dict] = []
    try:
        async with AsyncSessionLocal() as session:
            repo = IncidentRepository(session)
            incidents = await repo.search(keywords, limit=5)
            for inc in incidents:
                memory_matches.append({
                    "incident_id": str(inc.incident_id),
                    "date": inc.incident_date.isoformat() if inc.incident_date else None,
                    "type": inc.incident_type,
                    "title": inc.title,
                    "summary": inc.summary,
                    "root_causes": inc.root_causes or [],
                    "actions_taken": inc.actions_taken or [],
                    "outcome": inc.outcome_summary or "",
                    "resolved": inc.resolved,
                    "confidence": float(inc.confidence) if inc.confidence is not None else None,
                    "affected_domains": inc.affected_domains or [],
                })
    except Exception as exc:
        logger.error("recall_db_error", error=str(exc))

    logger.info("recall_matches", count=len(memory_matches))
    t1 = _now()

    return {
        "memory_matches": memory_matches,
        "messages": [AIMessage(content=f"[recall] Found {len(memory_matches)} past incident(s) matching query.")],
    }

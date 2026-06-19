"""Memory agent -- retrieves semantically similar past incidents via pgvector."""

from __future__ import annotations

from typing import Any

import structlog
from langchain_core.messages import AIMessage

from ai_ops_engine.embeddings import embed_text
from ai_ops_engine.graph.state import AgentState

logger = structlog.get_logger(__name__)


def _serialise_incident(inc: Any) -> dict[str, Any]:
    """Convert an Incident ORM object into the graph memory match shape."""
    return {
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
    }


async def memory_agent(state: AgentState) -> dict[str, Any]:
    """Retrieve past incidents semantically similar to the current query."""
    query = state["user_query"]

    try:
        query_embedding = await embed_text(query)
    except Exception as exc:
        logger.error("memory_agent_embedding_failed", error=str(exc))
        return {
            "memory_matches": [],
            "messages": [
                AIMessage(content="[memory_agent] Embedding generation failed.")
            ],
        }

    from backend.db.connection import AsyncSessionLocal
    from backend.db.repositories.approvals import IncidentRepository

    memory_matches: list[dict[str, Any]] = []
    try:
        async with AsyncSessionLocal() as session:
            repo = IncidentRepository(session)
            incidents = await repo.search_by_embedding(query_embedding, limit=5)
            memory_matches = [_serialise_incident(inc) for inc in incidents]
    except Exception as exc:
        logger.error("memory_agent_db_error", error=str(exc))

    logger.info("memory_agent_results", count=len(memory_matches))

    return {
        "memory_matches": memory_matches,
        "messages": [
            AIMessage(
                content=(
                    f"[memory_agent] Found {len(memory_matches)} relevant "
                    "past incident(s)."
                )
            )
        ],
    }

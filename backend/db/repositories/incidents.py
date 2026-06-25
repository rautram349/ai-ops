"""Repository for Incident persistence."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

import structlog
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.agent import Incident

logger = structlog.get_logger(__name__)


class IncidentRepository:
    """Data-access layer for the incident memory store.

    Args:
        session: An open async SQLAlchemy session (injected via ``get_db``).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _build_embedding_text(
        *,
        title: str,
        summary: str,
        root_causes: list[dict[str, Any]],
        actions_taken: list[dict[str, Any]] | None,
        outcome_summary: str | None,
    ) -> str:
        """Build rich incident text for semantic embedding generation."""
        parts = [f"Title:\n{title}", f"Summary:\n{summary}"]

        if root_causes:
            causes_text = "\n".join(
                rc.get("cause", str(rc)) if isinstance(rc, dict) else str(rc)
                for rc in root_causes
            )
            parts.append(f"Root causes:\n{causes_text}")

        if actions_taken:
            actions_text = "\n".join(
                a.get("action", str(a)) if isinstance(a, dict) else str(a)
                for a in actions_taken
            )
            parts.append(f"Actions taken:\n{actions_text}")

        if outcome_summary:
            parts.append(f"Outcome:\n{outcome_summary}")

        return "\n\n".join(parts)

    async def _generate_embedding(self, text: str) -> Any | None:
        """Generate a pgvector embedding for the given text, returning None on failure."""
        try:
            from ai_ops_engine.embeddings import embed_text
            return await embed_text(text)
        except Exception as exc:
            logger.warning("embedding_generation_failed", error=str(exc))
            return None

    async def create(
        self,
        *,
        conversation_id: uuid.UUID | None,
        incident_date: date,
        incident_type: str,
        title: str,
        summary: str,
        affected_domains: list[str],
        root_causes: list[dict[str, Any]],
        affected_products: list[str] | None = None,
        affected_regions: list[str] | None = None,
        actions_taken: list[dict[str, Any]] | None = None,
        outcome_summary: str | None = None,
        confidence: float | None = None,
    ) -> Incident:
        """Persist a new incident record."""
        incident = Incident(
            conversation_id=conversation_id,
            incident_date=incident_date,
            incident_type=incident_type,
            title=title,
            summary=summary,
            affected_domains=affected_domains,
            affected_products=affected_products,
            affected_regions=affected_regions,
            root_causes=root_causes,
            actions_taken=actions_taken,
            outcome_summary=outcome_summary,
            confidence=confidence,
        )

        embedding_text = self._build_embedding_text(
            title=title,
            summary=summary,
            root_causes=root_causes,
            actions_taken=actions_taken,
            outcome_summary=outcome_summary,
        )
        incident.embedding = await self._generate_embedding(embedding_text)

        self._session.add(incident)
        await self._session.flush()
        return incident

    async def get(self, incident_id: uuid.UUID) -> Incident | None:
        """Fetch an incident by primary key."""
        result = await self._session.execute(
            select(Incident).where(Incident.incident_id == incident_id)
        )
        return result.scalar_one_or_none()

    async def list_incidents(
        self,
        *,
        incident_type: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        resolved: bool | None = None,
        limit: int = 50,
    ) -> list[Incident]:
        """List incidents with optional date and type filters."""
        stmt = select(Incident).order_by(
            Incident.created_at.desc(),
        )
        if incident_type is not None:
            stmt = stmt.where(Incident.incident_type == incident_type)
        if start_date is not None:
            stmt = stmt.where(Incident.incident_date >= start_date)
        if end_date is not None:
            stmt = stmt.where(Incident.incident_date <= end_date)
        if resolved is not None:
            stmt = stmt.where(Incident.resolved == resolved)
        result = await self._session.execute(stmt.limit(limit))
        return list(result.scalars().all())

    async def search(
        self,
        keywords: list[str],
        incident_type: str | None = None,
        limit: int = 5,
    ) -> list[Incident]:
        """Full-text keyword search across incident title, summary and outcome."""
        if not keywords:
            return []

        conditions = []
        for kw in keywords:
            pattern = f"%{kw}%"
            conditions.append(
                or_(
                    Incident.title.ilike(pattern),
                    Incident.summary.ilike(pattern),
                    Incident.outcome_summary.ilike(pattern),
                )
            )

        stmt = (
            select(Incident)
            .where(or_(*conditions))
            .order_by(Incident.incident_date.desc(), Incident.created_at.desc())
        )
        if incident_type is not None:
            stmt = stmt.where(Incident.incident_type == incident_type)
        result = await self._session.execute(stmt.limit(limit))
        return list(result.scalars().all())

    async def search_by_embedding(
        self,
        query_embedding: list[float],
        limit: int = 5,
    ) -> list[Incident]:
        """Semantic similarity search using pgvector cosine distance."""
        stmt = (
            select(Incident)
            .where(Incident.embedding.isnot(None))
            .order_by(Incident.embedding.cosine_distance(query_embedding))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def resolve(
        self,
        incident_id: uuid.UUID,
        outcome_summary: str | None = None,
    ) -> None:
        """Mark an incident as resolved."""
        values: dict[str, Any] = {
            "resolved": True,
            "resolved_at": datetime.now(UTC).replace(tzinfo=None),
        }
        if outcome_summary is not None:
            values["outcome_summary"] = outcome_summary
        await self._session.execute(
            update(Incident)
            .where(Incident.incident_id == incident_id)
            .values(**values)
        )

    async def find_by_conversation(
        self,
        conversation_id: uuid.UUID,
        limit: int = 1,
    ) -> list[Incident]:
        """Find incidents by conversation ID, newest first."""
        result = await self._session.execute(
            select(Incident)
            .where(Incident.conversation_id == conversation_id)
            .order_by(Incident.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def update_after_execution(
        self,
        incident: Incident,
        actions_taken: list[dict[str, Any]],
        outcome_summary: str | None = None,
        resolved: bool = False,
    ) -> Incident:
        """Update an incident with execution results and regenerate its embedding."""
        existing_actions = incident.actions_taken or []
        incident.actions_taken = existing_actions + actions_taken

        if outcome_summary:
            incident.outcome_summary = outcome_summary

        if resolved:
            incident.resolved = True
            incident.resolved_at = datetime.now(UTC).replace(tzinfo=None)

        embedding_text = self._build_embedding_text(
            title=incident.title,
            summary=incident.summary,
            root_causes=incident.root_causes or [],
            actions_taken=incident.actions_taken,
            outcome_summary=incident.outcome_summary,
        )
        incident.embedding = await self._generate_embedding(embedding_text)

        await self._session.flush()
        return incident

    async def exists_for_date_type(
        self,
        incident_type: str,
        incident_date: date,
    ) -> bool:
        """Return True if an incident of incident_type already exists for incident_date."""
        result = await self._session.execute(
            select(Incident.incident_id)
            .where(
                Incident.incident_type == incident_type,
                Incident.incident_date == incident_date,
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

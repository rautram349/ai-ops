"""Repository for ApprovalRequest, ExecutedAction, and Incident persistence."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

import structlog
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.agent import ApprovalRequest, ExecutedAction, Incident

logger = structlog.get_logger(__name__)


class ApprovalRepository:
    """Data-access layer for approval requests and executed actions.

    Args:
        session: An open async SQLAlchemy session (injected via ``get_db``).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_approval(
        self,
        *,
        conversation_id: uuid.UUID | None,
        action_type: str,
        target_entities: dict[str, Any] | list[str],
        reason: str,
        expected_impact: str | None,
        risk_level: str,
        reversible: bool,
    ) -> ApprovalRequest:
        """Persist a new pending approval request.

        Args:
            conversation_id: UUID of the parent conversation.
            action_type: e.g. ``'restock'``, ``'pause_campaign'``.
            target_entities: Product IDs, campaign IDs, or other targets.
            reason: Human-readable reason for the action.
            expected_impact: Description of expected outcome.
            risk_level: ``'low'``, ``'medium'``, or ``'high'``.
            reversible: Whether the action can be undone.

        Returns:
            The newly created ``ApprovalRequest`` instance.
        """
        # Normalise list → dict so the JSONB column always stores an object.
        entities: Any = (
            {"ids": target_entities}
            if isinstance(target_entities, list)
            else target_entities
        )
        approval = ApprovalRequest(
            conversation_id=conversation_id,
            action_type=action_type,
            target_entities=entities,
            reason=reason,
            expected_impact=expected_impact,
            risk_level=risk_level,
            reversible=reversible,
        )
        self._session.add(approval)
        await self._session.flush()
        return approval

    async def get_approval(
        self, approval_id: uuid.UUID
    ) -> ApprovalRequest | None:
        """Fetch an approval request by primary key.

        Args:
            approval_id: UUID of the approval request.

        Returns:
            The ``ApprovalRequest`` or ``None`` if not found.
        """
        result = await self._session.execute(
            select(ApprovalRequest).where(
                ApprovalRequest.approval_id == approval_id
            )
        )
        return result.scalar_one_or_none()

    async def list_approvals(
        self,
        status: str | None = None,
        conversation_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list[ApprovalRequest]:
        """List approval requests with optional filters.

        Args:
            status: Filter by status (``'pending'``, ``'approved'``,
                ``'rejected'``). ``None`` returns all.
            conversation_id: Restrict to a specific conversation.
            limit: Maximum number of results to return.

        Returns:
            A list of ``ApprovalRequest`` instances ordered by creation time.
        """
        stmt = select(ApprovalRequest).order_by(
            ApprovalRequest.created_at.desc()
        )
        if status is not None:
            stmt = stmt.where(ApprovalRequest.status == status)
        if conversation_id is not None:
            stmt = stmt.where(
                ApprovalRequest.conversation_id == conversation_id
            )
        result = await self._session.execute(stmt.limit(limit))
        return list(result.scalars().all())

    async def decide(
        self,
        approval_id: uuid.UUID,
        *,
        decision: str,
        decided_by: str,
        decision_note: str | None = None,
    ) -> ApprovalRequest | None:
        """Record an approve or reject decision on a pending request.

        Args:
            approval_id: UUID of the approval request.
            decision: ``'approved'`` or ``'rejected'``.
            decided_by: Identifier of the person making the decision.
            decision_note: Optional free-text note.

        Returns:
            The updated ``ApprovalRequest``, or ``None`` if not found.
        """
        approval = await self.get_approval(approval_id)
        if approval is None:
            return None
        await self._session.execute(
            update(ApprovalRequest)
            .where(ApprovalRequest.approval_id == approval_id)
            .values(
                status=decision,
                decided_at=datetime.now(timezone.utc).replace(tzinfo=None),
                decided_by=decided_by,
                decision_note=decision_note,
            )
        )
        await self._session.refresh(approval)
        return approval

    async def record_execution(
        self,
        *,
        approval_id: uuid.UUID | None,
        action_type: str,
        tool_name: str,
        arguments: dict[str, Any],
        result: dict[str, Any] | None,
        success: bool,
        error: str | None = None,
    ) -> ExecutedAction:
        """Persist the outcome of an executed write action.

        Args:
            approval_id: UUID of the approval that authorised this action.
            action_type: Same type as the parent approval request.
            tool_name: MCP tool that was called.
            arguments: Arguments passed to the tool.
            result: JSON response from the tool.
            success: Whether the tool call succeeded.
            error: Error message if the call failed.

        Returns:
            The persisted ``ExecutedAction`` instance.
        """
        ea = ExecutedAction(
            approval_id=approval_id,
            action_type=action_type,
            tool_name=tool_name,
            arguments=arguments,
            result=result,
            success=success,
            error=error,
        )
        self._session.add(ea)
        await self._session.flush()
        return ea


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
        """Persist a new incident record.

        Args:
            conversation_id: UUID of the conversation that surfaced the incident.
            incident_date: Calendar date the incident occurred.
            incident_type: Type tag matching INCIDENT_CALENDAR types.
            title: Short human-readable title.
            summary: Longer description of what happened.
            affected_domains: Domain names involved (e.g. ``['sales', 'inventory']``).
            root_causes: List of cause dicts with ``cause``, ``confidence``,
                ``domains`` keys.
            affected_products: Product IDs involved.
            affected_regions: Region names involved.
            actions_taken: List of action outcome dicts.
            outcome_summary: Free-text outcome description.
            confidence: Overall diagnosis confidence (0.0–1.0).

        Returns:
            The persisted ``Incident`` instance.
        """
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
        try:
            from ai_ops_engine.embeddings import embed_text

            incident.embedding = await embed_text(embedding_text)
        except Exception as exc:
            logger.warning("embedding_generation_failed", error=str(exc))

        self._session.add(incident)
        await self._session.flush()
        return incident

    async def get(self, incident_id: uuid.UUID) -> Incident | None:
        """Fetch an incident by primary key.

        Args:
            incident_id: UUID of the incident.

        Returns:
            The ``Incident`` or ``None`` if not found.
        """
        result = await self._session.execute(
            select(Incident).where(Incident.incident_id == incident_id)
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        *,
        incident_type: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        resolved: bool | None = None,
        limit: int = 50,
    ) -> list[Incident]:
        """List incidents with optional date and type filters.

        Args:
            incident_type: Filter by type string.
            start_date: Earliest incident date (inclusive).
            end_date: Latest incident date (inclusive).
            resolved: ``True`` / ``False`` to filter by resolution status.
            limit: Maximum number of results.

        Returns:
            A list of ``Incident`` instances ordered by date descending.
        """
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
        """Full-text keyword search across incident title, summary and outcome.

        Args:
            keywords: List of search terms (case-insensitive substring match).
            incident_type: Optional type filter applied on top of the keyword match.
            limit: Maximum number of results to return.

        Returns:
            A list of ``Incident`` instances ordered by incident date descending.
        """
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
        """Semantic similarity search using pgvector cosine distance.

        Computes cosine distance between the query vector and every stored
        incident embedding, returning the closest matches. The embedding
        column is only used for sorting -- full incident rows are returned.
        """
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
        """Mark an incident as resolved.

        Args:
            incident_id: UUID of the incident to resolve.
            outcome_summary: Optional description of how it was resolved.
        """
        values: dict[str, Any] = {
            "resolved": True,
            "resolved_at": datetime.now(timezone.utc).replace(tzinfo=None),
        }
        if outcome_summary is not None:
            values["outcome_summary"] = outcome_summary
        await self._session.execute(
            update(Incident)
            .where(Incident.incident_id == incident_id)
            .values(**values)
        )

    async def exists_for_date_type(
        self,
        incident_type: str,
        incident_date: date,
    ) -> bool:
        """Return ``True`` if an incident of *incident_type* already exists for *incident_date*.

        Used by the background scheduler to deduplicate same-day incidents.
        """
        result = await self._session.execute(
            select(Incident.incident_id)
            .where(
                Incident.incident_type == incident_type,
                Incident.incident_date == incident_date,
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

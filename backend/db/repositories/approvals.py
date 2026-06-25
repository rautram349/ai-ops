"""Repository for ApprovalRequest and ExecutedAction persistence."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.constants import DEFAULT_PAGE_LIMIT
from backend.models.agent import ApprovalRequest, ExecutedAction

logger = structlog.get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


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
        limit: int = DEFAULT_PAGE_LIMIT,
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
                decided_at=_utcnow(),
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



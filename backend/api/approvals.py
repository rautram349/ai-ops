"""Approvals router.

Endpoints:
    GET  /api/approvals                    - list approval requests (+ status filter)
    GET  /api/approvals/{id}               - get a single approval request
    POST /api/approvals/{id}/approve       - approve an action
    POST /api/approvals/{id}/reject        - reject an action
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_serializer
from sqlalchemy.ext.asyncio import AsyncSession

from ai_ops_engine.clients.mcp_client import get_mcp_client
from ai_ops_engine.graph.write_tools import WRITE_TOOL_SERVER as _TOOL_SERVER_MAP
from backend.db.connection import get_db
from backend.db.repositories import ApprovalRepository, IncidentRepository

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


# ── Schemas ───────────────────────────────────────────────────────────────────


class ApprovalOut(BaseModel):
    approval_id: uuid.UUID
    conversation_id: uuid.UUID | None
    action_type: str
    target_entities: dict[str, Any]
    reason: str
    expected_impact: str | None
    risk_level: str
    reversible: bool
    status: str
    created_at: datetime
    decided_at: datetime | None
    decided_by: str | None
    decision_note: str | None

    model_config = {"from_attributes": True}

    @field_serializer("created_at", "decided_at")
    def _utc_z(self, v: datetime | None) -> str | None:
        if v is None:
            return None
        return v.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class ApprovalListOut(BaseModel):
    approvals: list[ApprovalOut]


class DecisionRequest(BaseModel):
    decided_by: str = "user"
    note: str | None = None


class ExecutionOut(BaseModel):
    approval_id: uuid.UUID
    success: bool
    result: dict[str, Any] | None = None
    error: str | None = None
    executed_at: datetime


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("", response_model=ApprovalListOut)
async def list_approvals(
    status: str | None = None,
    conversation_id: uuid.UUID | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> ApprovalListOut:
    """List approval requests with optional filters.

    Args:
        status: Filter by status (``'pending'``, ``'approved'``,
            ``'rejected'``). Pass ``'all'`` or omit to return all.
        conversation_id: Restrict to a specific conversation.
        limit: Maximum number of results (default 50).
        db: Injected async database session.

    Returns:
        Paginated list of approval request objects.
    """
    repo = ApprovalRepository(db)
    # "all" means no status filter
    status_filter = None if (status is None or status == "all") else status
    approvals = await repo.list_approvals(
        status=status_filter,
        conversation_id=conversation_id,
        limit=limit,
    )
    return ApprovalListOut(
        approvals=[ApprovalOut.model_validate(a) for a in approvals]
    )


@router.get("/{approval_id}", response_model=ApprovalOut)
async def get_approval(
    approval_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ApprovalOut:
    """Get a single approval request by ID.

    Args:
        approval_id: UUID of the approval request.
        db: Injected async database session.

    Returns:
        The approval request detail.

    Raises:
        HTTPException: 404 if the approval is not found.
    """
    repo = ApprovalRepository(db)
    approval = await repo.get_approval(approval_id)
    if approval is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Approval {approval_id} not found.",
        )
    return ApprovalOut.model_validate(approval)


@router.post("/{approval_id}/approve", response_model=ApprovalOut)
async def approve_action(
    approval_id: uuid.UUID,
    body: DecisionRequest,
    db: AsyncSession = Depends(get_db),
) -> ApprovalOut:
    """Approve a pending action request.

    Args:
        approval_id: UUID of the approval request.
        body: Decision payload with ``decided_by`` and optional ``note``.
        db: Injected async database session.

    Returns:
        The updated approval request.

    Raises:
        HTTPException: 404 if not found; 409 if not in pending state.
    """
    repo = ApprovalRepository(db)
    approval = await repo.get_approval(approval_id)
    if approval is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Approval {approval_id} not found.",
        )
    if approval.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Approval is already in '{approval.status}' state.",
        )
    updated = await repo.decide(
        approval_id,
        decision="approved",
        decided_by=body.decided_by,
        decision_note=body.note,
    )
    # Commit NOW so the status change is visible to the /execute request that
    # arrives immediately after this response is sent. Without this explicit
    # commit the FastAPI dependency cleanup commits *after* the response bytes
    # are flushed, creating a race where /execute reads the old "pending" row.
    await db.commit()
    return ApprovalOut.model_validate(updated)


@router.post("/{approval_id}/reject", response_model=ApprovalOut)
async def reject_action(
    approval_id: uuid.UUID,
    body: DecisionRequest,
    db: AsyncSession = Depends(get_db),
) -> ApprovalOut:
    """Reject a pending action request.

    Args:
        approval_id: UUID of the approval request.
        body: Decision payload with ``decided_by`` and optional ``note``.
        db: Injected async database session.

    Returns:
        The updated approval request.

    Raises:
        HTTPException: 404 if not found; 409 if not in pending state.
    """
    repo = ApprovalRepository(db)
    approval = await repo.get_approval(approval_id)
    if approval is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Approval {approval_id} not found.",
        )
    if approval.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Approval is already in '{approval.status}' state.",
        )
    updated = await repo.decide(
        approval_id,
        decision="rejected",
        decided_by=body.decided_by,
        decision_note=body.note,
    )
    await db.commit()  # Same race-condition fix as approve_action above.
    return ApprovalOut.model_validate(updated)


@router.post("/{approval_id}/execute", response_model=ExecutionOut)
async def execute_action(
    approval_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ExecutionOut:
    """Execute an approved write action via the appropriate MCP server.

    Args:
        approval_id: UUID of the approval request (must be in 'approved' state).
        db: Injected async database session.

    Returns:
        Execution outcome with success flag, result data, and timestamp.

    Raises:
        HTTPException: 404 if not found; 409 if not in 'approved' state;
            422 if the action type has no registered MCP server.
    """
    repo = ApprovalRepository(db)
    approval = await repo.get_approval(approval_id)
    if approval is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Approval {approval_id} not found.",
        )
    if approval.status != "approved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Approval is in '{approval.status}' state, expected 'approved'.",
        )
    server = _TOOL_SERVER_MAP.get(approval.action_type)
    if server is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"No MCP server registered for action type '{approval.action_type}'.",
        )

    client = get_mcp_client()
    now = datetime.now(UTC).replace(tzinfo=None)
    arguments = dict(approval.target_entities or {})

    # ── Argument normalisation ──────────────────────────────────────────────
    # The LLM sometimes stores apply_discount args with `product_id` (singular)
    # instead of the tool's required `product_ids` (list).  Normalise here so
    # the MCP call always gets the right shape.
    if approval.action_type == "apply_discount":
        if "product_id" in arguments and "product_ids" not in arguments:
            pid = arguments.pop("product_id")
            arguments["product_ids"] = [pid] if isinstance(pid, str) else pid
        elif "product_ids" in arguments and isinstance(arguments["product_ids"], str):
            arguments["product_ids"] = [arguments["product_ids"]]

    try:
        raw = await client.call_tool(server, approval.action_type, arguments)
        result_dict: dict[str, Any] = (
            raw if isinstance(raw, dict) else {"result": str(raw)[:1000]}
        )
        await repo.record_execution(
            approval_id=approval_id,
            action_type=approval.action_type,
            tool_name=approval.action_type,
            arguments=arguments,
            result=result_dict,
            success=True,
        )

        # ── Backfill incident with execution result ────────────────────────
        if approval.conversation_id is not None:
            try:
                incident_repo = IncidentRepository(db)
                incidents = await incident_repo.find_by_conversation(
                    approval.conversation_id, limit=1
                )
                if incidents:
                    action_record = {
                        "action_type": approval.action_type,
                        "tool": approval.action_type,
                        "server": server,
                        "arguments": arguments,
                        "result": result_dict,
                        "success": True,
                    }
                    outcome = (
                        f"Executed {approval.action_type} on "
                        f"{server} — success"
                    )
                    await incident_repo.update_after_execution(
                        incident=incidents[0],
                        actions_taken=[action_record],
                        outcome_summary=outcome,
                        resolved=True,
                    )
            except Exception as inc_exc:
                logger.warning("incident_backfill_failed", error=str(inc_exc))
        # ────────────────────────────────────────────────────────────────────

        await db.commit()
        return ExecutionOut(
            approval_id=approval_id,
            success=True,
            result=result_dict,
            error=None,
            executed_at=now,
        )
    except Exception as exc:
        error_msg = str(exc)
        await repo.record_execution(
            approval_id=approval_id,
            action_type=approval.action_type,
            tool_name=approval.action_type,
            arguments=arguments,
            result=None,
            success=False,
            error=error_msg,
        )
        await db.commit()
        return ExecutionOut(
            approval_id=approval_id,
            success=False,
            result=None,
            error=error_msg,
            executed_at=now,
        )

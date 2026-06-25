"""Incident history router.

Endpoints:
    GET /api/incidents              - list incidents with optional filters
    GET /api/incidents/{id}         - get a single incident with full detail
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_serializer
from sqlalchemy.ext.asyncio import AsyncSession

from backend.constants import DEFAULT_PAGE_LIMIT
from backend.db.connection import get_db
from backend.db.repositories import IncidentRepository

router = APIRouter(prefix="/api/incidents", tags=["incidents"])


# ── Schemas ───────────────────────────────────────────────────────────────────


class IncidentOut(BaseModel):
    incident_id: uuid.UUID
    conversation_id: uuid.UUID | None
    incident_date: date
    incident_type: str
    title: str
    summary: str
    affected_domains: list[str]
    affected_products: list[str] | None
    affected_regions: list[str] | None
    root_causes: list[dict[str, Any]]
    actions_taken: list[dict[str, Any]] | None
    outcome_summary: str | None
    confidence: float | None
    resolved: bool
    created_at: datetime
    resolved_at: datetime | None

    model_config = {"from_attributes": True}

    @field_serializer("created_at", "resolved_at")
    def _utc_z(self, v: datetime | None) -> str | None:
        if v is None:
            return None
        return v.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("", response_model=list[IncidentOut])
async def list_incidents(
    incident_type: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    resolved: bool | None = None,
    limit: int = DEFAULT_PAGE_LIMIT,
    db: AsyncSession = Depends(get_db),
) -> list[IncidentOut]:
    """List past incidents with optional filters.

    Args:
        incident_type: Filter by incident type string.
        start_date: Earliest incident date (inclusive).
        end_date: Latest incident date (inclusive).
        resolved: ``true`` / ``false`` to filter by resolution status.
        limit: Maximum number of results (default 50).
        db: Injected async database session.

    Returns:
        A list of incident summaries ordered by date descending.
    """
    repo = IncidentRepository(db)
    incidents = await repo.list_incidents(
        incident_type=incident_type,
        start_date=start_date,
        end_date=end_date,
        resolved=resolved,
        limit=limit,
    )
    return [IncidentOut.model_validate(i) for i in incidents]


@router.get("/{incident_id}", response_model=IncidentOut)
async def get_incident(
    incident_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> IncidentOut:
    """Get full detail for a single incident.

    Args:
        incident_id: UUID of the incident.
        db: Injected async database session.

    Returns:
        Full incident record including root causes and actions taken.

    Raises:
        HTTPException: 404 if the incident is not found.
    """
    repo = IncidentRepository(db)
    incident = await repo.get(incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident {incident_id} not found.",
        )
    return IncidentOut.model_validate(incident)


class ResolveRequest(BaseModel):
    outcome_summary: str | None = None


@router.patch("/{incident_id}/resolve", response_model=IncidentOut)
async def resolve_incident(
    incident_id: uuid.UUID,
    body: ResolveRequest,
    db: AsyncSession = Depends(get_db),
) -> IncidentOut:
    """Mark an incident as resolved.

    Args:
        incident_id: UUID of the incident to resolve.
        body: Optional outcome summary describing how the incident was resolved.
        db: Injected async database session.

    Returns:
        The updated incident record.

    Raises:
        HTTPException: 404 if the incident is not found.
    """
    repo = IncidentRepository(db)
    incident = await repo.get(incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident {incident_id} not found.",
        )
    await repo.resolve(incident_id, outcome_summary=body.outcome_summary)
    await db.commit()
    updated = await repo.get(incident_id)
    return IncidentOut.model_validate(updated)

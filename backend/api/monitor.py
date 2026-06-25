"""Monitor API router.

Endpoints:
    GET /api/monitor/status   — latest run result + new incident count
    GET /api/monitor/runs     — last 20 runs in reverse-chronological order
    POST /api/monitor/trigger — immediately fire the monitor job (debug)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, field_serializer

from backend.core.config import settings
from backend.services import monitor_run_store as store

router = APIRouter(prefix="/api/monitor", tags=["monitor"])


# ── Response schemas ──────────────────────────────────────────────────────────

class RunSchema(BaseModel):
    triggered_at: datetime
    status: str
    check_date: str | None
    anomalies_found: int
    incidents_created: int
    duration_ms: int | None
    error: str | None
    detail: list[dict[str, Any]]

    @field_serializer("triggered_at")
    def _serialize_triggered_at(self, dt: datetime) -> str:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


class MonitorStatusResponse(BaseModel):
    last_run: RunSchema | None
    next_run_at: datetime | None
    interval_minutes: int
    new_incident_count: int

    @field_serializer("next_run_at")
    def _serialize_next_run_at(self, dt: datetime | None) -> str | None:
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/status", response_model=MonitorStatusResponse)
async def get_monitor_status(since: str | None = None) -> MonitorStatusResponse:
    """Return the latest monitor run and the count of new incidents.

    Query params:
        since: ISO-8601 UTC datetime string.  When supplied, ``new_incident_count``
               only counts incidents created by runs *after* this timestamp.
    """
    since_dt: datetime | None = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError:
            since_dt = None

    latest = store.get_latest()
    next_run = store.get_next_run_at()
    new_count = store.count_new_incidents_since(since_dt)

    last_run: RunSchema | None = None
    if latest is not None:
        last_run = RunSchema(
            triggered_at=latest.triggered_at,
            status=latest.status,
            check_date=latest.check_date,
            anomalies_found=latest.anomalies_found,
            incidents_created=latest.incidents_created,
            duration_ms=latest.duration_ms,
            error=latest.error,
            detail=latest.detail,
        )

    return MonitorStatusResponse(
        last_run=last_run,
        next_run_at=next_run,
        interval_minutes=settings.monitor_interval_minutes,
        new_incident_count=new_count,
    )


@router.get("/runs", response_model=list[RunSchema])
async def get_monitor_runs() -> list[RunSchema]:
    """Return the last 20 monitor runs, newest first."""
    return [
        RunSchema(
            triggered_at=r.triggered_at,
            status=r.status,
            check_date=r.check_date,
            anomalies_found=r.anomalies_found,
            incidents_created=r.incidents_created,
            duration_ms=r.duration_ms,
            error=r.error,
            detail=r.detail,
        )
        for r in store.get_all()
    ]


@router.post("/trigger", status_code=202)
async def trigger_monitor() -> dict[str, str]:
    """Immediately fire the monitor job (for debugging / manual refresh)."""
    from backend.scheduler import trigger_now

    trigger_now()
    return {"status": "triggered"}

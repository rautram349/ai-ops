"""Health-check router."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    version: str = "0.1.0"


@router.get("/health", response_model=HealthResponse, tags=["ops"])
async def health() -> HealthResponse:
    """Return service liveness status.

    Returns:
        A simple ``{"status": "ok"}`` payload.
    """
    return HealthResponse(status="ok")

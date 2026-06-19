"""Chat router — the primary entry point for user queries.

Endpoint:
    POST /api/chat        – submit a query, receive a structured investigation response
    POST /api/chat/stream – same, but as Server-Sent Events with node-progress events

The graph invocation is delegated to ``backend.services.chat_service``.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from backend.db.connection import get_db
from backend.services.chat_service import ChatService
from ai_ops_engine.graph.builder import stream_graph_events

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


# ── Request / response schemas ────────────────────────────────────────────────


class ChatRequest(BaseModel):
    """Body for POST /api/chat."""

    conversation_id: uuid.UUID | None = None
    message: str


class FindingOut(BaseModel):
    title: str
    detail: str
    severity: str = "info"  # "info" | "warning" | "critical"


class RecommendedActionOut(BaseModel):
    action_type: str
    reason: str
    risk_level: str = "low"   # "low" | "medium" | "high"
    reversible: bool = True


class PendingApprovalOut(BaseModel):
    tool: str
    server: str
    arguments: dict[str, Any] = {}
    reason: str = ""
    approval_id: str | None = None
    risk_level: str = "medium"
    reversible: bool = True


class ChatResponsePayload(BaseModel):
    summary: str
    findings: list[FindingOut] = []
    recommendations: list[RecommendedActionOut] = []
    actions_taken: list[str] = []
    pending_approvals: list[PendingApprovalOut] = []


class ChatOut(BaseModel):
    conversation_id: uuid.UUID
    message_id: uuid.UUID
    intent: str
    status: str
    response: ChatResponsePayload


# ── Route ─────────────────────────────────────────────────────────────────────


@router.post(
    "/chat",
    response_model=ChatOut,
    status_code=status.HTTP_200_OK,
)
async def chat(
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
) -> ChatOut:
    """Submit a user query and receive a structured investigation response.

    Creates or resumes a conversation, triggers the LangGraph orchestration
    engine, and returns the investigation result.

    Args:
        body: Request payload containing an optional ``conversation_id`` and
            the user ``message``.
        db: Injected async database session.

    Returns:
        Structured investigation result with findings, root causes, and
        recommended actions.
    """
    service = ChatService(db)
    result = await service.handle(
        message=body.message,
        conversation_id=body.conversation_id,
    )
    return result


# ── Streaming route ───────────────────────────────────────────────────────────


@router.post("/chat/stream")
async def chat_stream(
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
) -> EventSourceResponse:
    """Submit a user query and receive node-progress + result as Server-Sent Events.

    SSE event shapes:
        {"type": "conversation_ready", "conversation_id": "..."}
        {"type": "node_start","node": "route"|"diagnose"|"plan"|"respond"|...}
        {"type": "done",      "conversation_id": "...", "message_id": "...",
                              "intent": "...", "status": "completed",
                              "response": {...}}
        {"type": "error",     "message": "..."}

    The ``conversation_ready`` event fires before the graph starts so the frontend
    can navigate immediately without waiting for the full graph execution.
    """
    service = ChatService(db)

    # Set up the conversation BEFORE opening the stream so the ID is real.
    setup = await service.setup_stream(
        message=body.message,
        conversation_id=body.conversation_id,
    )

    async def generator() -> Any:
        try:
            # First event: hand the frontend the conversation ID it needs to navigate.
            yield {
                "data": json.dumps({
                    "type":            "conversation_ready",
                    "conversation_id": str(setup["conversation_id"]),
                })
            }

            # Stream node-progress events; collect the final AgentState.
            final_state: dict[str, Any] | None = None
            async for event in stream_graph_events(setup["initial_state"]):
                if event["type"] == "final":
                    final_state = event["state"]
                else:
                    yield {"data": json.dumps(event)}

            if final_state is None:
                logger.error("stream_no_final_state", conversation_id=str(setup["conversation_id"]))
                yield {"data": json.dumps({"type": "error", "message": "Graph produced no output"})}
                return

            # Persist everything and get the ChatOut-shaped payload.
            result = await service.finalize_stream(setup, final_state)
            yield {"data": json.dumps({"type": "done", **result})}

        except Exception as exc:
            logger.exception("chat_stream_error", conversation_id=str(setup["conversation_id"]))
            yield {"data": json.dumps({"type": "error", "message": str(exc)})}

    return EventSourceResponse(generator())

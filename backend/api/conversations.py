"""Conversation management router.

Endpoints:
    GET    /api/conversations           – list active conversations
    GET    /api/conversations/{id}      – get conversation with messages
    PATCH  /api/conversations/{id}      – update conversation title
    DELETE /api/conversations/{id}      – archive a conversation
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_serializer
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.connection import get_db
from backend.db.repositories import ConversationRepository

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


# ── Response schemas ──────────────────────────────────────────────────────────


class MessageOut(BaseModel):
    message_id: uuid.UUID
    role: str
    content: str
    structured_response: dict[str, Any] | None
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_serializer("created_at")
    def _utc_z(self, v: datetime) -> str:
        return v.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class ConversationOut(BaseModel):
    conversation_id: uuid.UUID
    title: str | None
    started_at: datetime
    last_activity: datetime
    status: str

    model_config = {"from_attributes": True}

    @field_serializer("started_at", "last_activity")
    def _utc_z(self, v: datetime) -> str:
        return v.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class ConversationDetailOut(ConversationOut):
    messages: list[MessageOut] = []


class ConversationTitleUpdate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200, strip_whitespace=True)


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("", response_model=list[ConversationOut])
async def list_conversations(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> list[ConversationOut]:
    """List active conversations ordered by most recent activity.

    Args:
        limit: Maximum number of conversations to return (default 50).
        db: Injected async database session.

    Returns:
        A list of conversation summaries.
    """
    repo = ConversationRepository(db)
    convos = await repo.list(limit=limit)
    return [ConversationOut.model_validate(c) for c in convos]


@router.get("/{conversation_id}", response_model=ConversationDetailOut)
async def get_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ConversationDetailOut:
    """Get a conversation with its full message history.

    Args:
        conversation_id: UUID of the conversation.
        db: Injected async database session.

    Returns:
        Conversation detail including all messages.

    Raises:
        HTTPException: 404 if the conversation is not found.
    """
    repo = ConversationRepository(db)
    convo = await repo.get_with_messages(conversation_id)
    if convo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found.",
        )
    return ConversationDetailOut.model_validate(convo)


@router.patch("/{conversation_id}", response_model=ConversationOut)
async def update_conversation_title(
    conversation_id: uuid.UUID,
    body: ConversationTitleUpdate,
    db: AsyncSession = Depends(get_db),
) -> ConversationOut:
    """Update the title of a conversation.

    Args:
        conversation_id: UUID of the conversation.
        body: Request body containing the new title.
        db: Injected async database session.

    Returns:
        The updated conversation summary.

    Raises:
        HTTPException: 404 if the conversation is not found.
    """
    repo = ConversationRepository(db)
    convo = await repo.get(conversation_id)
    if convo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found.",
        )
    await repo.update_title(conversation_id, body.title)
    convo.title = body.title.strip()
    return ConversationOut.model_validate(convo)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Archive (soft-delete) a conversation.

    Args:
        conversation_id: UUID of the conversation to archive.
        db: Injected async database session.

    Raises:
        HTTPException: 404 if the conversation is not found.
    """
    repo = ConversationRepository(db)
    convo = await repo.get(conversation_id)
    if convo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found.",
        )
    await repo.archive(conversation_id)

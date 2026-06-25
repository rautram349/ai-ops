"""Repository for Conversation and Message persistence."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models.agent import Conversation, Message


class ConversationRepository:
    """Data-access layer for conversations and messages.

    Args:
        session: An open async SQLAlchemy session (injected via ``get_db``).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, title: str | None = None) -> Conversation:
        """Create and persist a new conversation.

        Args:
            title: Optional human-readable title.

        Returns:
            The newly created ``Conversation`` instance.
        """
        convo = Conversation(title=title)
        self._session.add(convo)
        await self._session.flush()
        return convo

    async def get(self, conversation_id: uuid.UUID) -> Conversation | None:
        """Fetch a conversation by primary key (without messages).

        Args:
            conversation_id: UUID of the conversation.

        Returns:
            The ``Conversation`` or ``None`` if not found.
        """
        result = await self._session.execute(
            select(Conversation).where(
                Conversation.conversation_id == conversation_id
            )
        )
        return result.scalar_one_or_none()

    async def get_with_messages(
        self, conversation_id: uuid.UUID
    ) -> Conversation | None:
        """Fetch a conversation eagerly loading its messages.

        Args:
            conversation_id: UUID of the conversation.

        Returns:
            The ``Conversation`` with ``messages`` populated, or ``None``.
        """
        result = await self._session.execute(
            select(Conversation)
            .where(Conversation.conversation_id == conversation_id)
            .options(selectinload(Conversation.messages))
        )
        return result.scalar_one_or_none()

    async def list(self, limit: int = 50) -> list[Conversation]:
        """List active conversations ordered by most recent activity.

        Args:
            limit: Maximum number of conversations to return.

        Returns:
            A list of ``Conversation`` instances.
        """
        result = await self._session.execute(
            select(Conversation)
            .where(Conversation.status == "active")
            .order_by(Conversation.last_activity.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def touch(self, conversation_id: uuid.UUID) -> None:
        """Update ``last_activity`` timestamp to now.

        Args:
            conversation_id: UUID of the conversation to touch.
        """
        await self._session.execute(
            update(Conversation)
            .where(Conversation.conversation_id == conversation_id)
            .values(last_activity=datetime.now(UTC).replace(tzinfo=None))
        )

    async def archive(self, conversation_id: uuid.UUID) -> None:
        """Set a conversation status to ``'archived'``.

        Args:
            conversation_id: UUID of the conversation to archive.
        """
        await self._session.execute(
            update(Conversation)
            .where(Conversation.conversation_id == conversation_id)
            .values(status="archived")
        )

    async def update_title(
        self, conversation_id: uuid.UUID, title: str
    ) -> None:
        """Update the human-readable title of a conversation.

        Args:
            conversation_id: UUID of the conversation.
            title: New title string (will be stripped of whitespace).
        """
        await self._session.execute(
            update(Conversation)
            .where(Conversation.conversation_id == conversation_id)
            .values(title=title.strip())
        )

    async def add_message(
        self,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
        structured_response: dict[str, Any] | None = None,
    ) -> Message:
        """Append a message to an existing conversation.

        Args:
            conversation_id: UUID of the parent conversation.
            role: ``'user'``, ``'assistant'``, or ``'system'``.
            content: Plain-text message body.
            structured_response: Optional JSON payload (for assistant messages).

        Returns:
            The persisted ``Message`` instance.
        """
        msg = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            structured_response=structured_response,
        )
        self._session.add(msg)
        await self._session.flush()
        return msg

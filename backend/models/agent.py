"""SQLAlchemy ORM models for all agent system tables.

These models map to the tables created by
``db/migrations/001_initial_schema.sql``. Business-data tables (orders,
products, etc.) are accessed read-only via the MCP servers and are not
modelled here.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.connection import Base


# ── Conversation & messaging ──────────────────────────────────────────────────


class Conversation(Base):
    """Persistent chat session between a user and the system."""

    __tablename__ = "conversations"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    title: Mapped[str | None] = mapped_column(String(300))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now()
    )
    last_activity: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now()
    )
    status: Mapped[str] = mapped_column(String(20), server_default="active")
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, server_default="{}"
    )

    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
    incidents: Mapped[list[Incident]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
    approvals: Mapped[list[ApprovalRequest]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class Message(Base):
    """A single user or assistant message within a conversation."""

    __tablename__ = "messages"

    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.conversation_id")
    )
    role: Mapped[str] = mapped_column(String(10))  # user | assistant | system
    content: Mapped[str] = mapped_column(Text)
    structured_response: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now()
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


# ── Approval & action tracking ────────────────────────────────────────────────


class ApprovalRequest(Base):
    """A proposed action awaiting human approval before execution."""

    __tablename__ = "approval_requests"

    approval_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.conversation_id"), nullable=True
    )
    action_type: Mapped[str] = mapped_column(String(50))
    target_entities: Mapped[dict[str, Any]] = mapped_column(JSONB)
    reason: Mapped[str] = mapped_column(Text)
    expected_impact: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_level: Mapped[str] = mapped_column(String(10))
    reversible: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(20), server_default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now()
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True
    )
    decided_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    conversation: Mapped[Conversation | None] = relationship(back_populates="approvals")
    executed_action: Mapped[ExecutedAction | None] = relationship(
        back_populates="approval"
    )


class ExecutedAction(Base):
    """Record of a write-tool execution that followed an approved request."""

    __tablename__ = "executed_actions"

    execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("approval_requests.approval_id"),
        nullable=True,
    )
    action_type: Mapped[str] = mapped_column(String(50))
    tool_name: Mapped[str] = mapped_column(String(100))
    arguments: Mapped[dict[str, Any]] = mapped_column(JSONB)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now()
    )

    approval: Mapped[ApprovalRequest | None] = relationship(
        back_populates="executed_action"
    )


# ── Incident memory ───────────────────────────────────────────────────────────


class Incident(Base):
    """A diagnosed incident stored for future recall and pattern matching."""

    __tablename__ = "incidents"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.conversation_id"), nullable=True
    )
    incident_date: Mapped[date] = mapped_column(Date)
    incident_type: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(Text)
    affected_domains: Mapped[list[str]] = mapped_column(ARRAY(String))
    affected_products: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True
    )
    affected_regions: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True
    )
    root_causes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    actions_taken: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB, nullable=True
    )
    outcome_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True
    )
    embedding: Mapped[Any | None] = mapped_column(Vector(1536), nullable=True)

    conversation: Mapped[Conversation | None] = relationship(
        back_populates="incidents"
    )

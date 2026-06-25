"""Database status string constants."""

from __future__ import annotations


class ApprovalStatus:
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ConversationStatus:
    ACTIVE = "active"
    ARCHIVED = "archived"

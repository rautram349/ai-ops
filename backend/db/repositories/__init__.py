"""Repository package for the backend data-access layer."""

from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.repositories.approvals import ApprovalRepository
from backend.db.repositories.conversations import ConversationRepository
from backend.db.repositories.incidents import IncidentRepository


def get_approval_repo(db: AsyncSession) -> ApprovalRepository:
    return ApprovalRepository(db)


def get_incident_repo(db: AsyncSession) -> IncidentRepository:
    return IncidentRepository(db)


__all__ = [
    "ApprovalRepository",
    "ConversationRepository",
    "IncidentRepository",
    "get_approval_repo",
    "get_incident_repo",
]

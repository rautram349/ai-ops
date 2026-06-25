"""Domain exception hierarchy for the AI-ops backend.

Raise these from service and API layers; the FastAPI exception handlers in
``backend/app.py`` map them to the correct HTTP status codes.
"""

from __future__ import annotations


class AiOpsError(Exception):
    """Base for all application exceptions."""


# ── Resource not found (→ HTTP 404) ──────────────────────────────────────────

class NotFoundError(AiOpsError):
    pass


class ConversationNotFoundError(NotFoundError):
    def __init__(self, conversation_id: object) -> None:
        super().__init__(f"Conversation {conversation_id} not found.")


class ApprovalNotFoundError(NotFoundError):
    def __init__(self, approval_id: object) -> None:
        super().__init__(f"Approval {approval_id} not found.")


class IncidentNotFoundError(NotFoundError):
    def __init__(self, incident_id: object) -> None:
        super().__init__(f"Incident {incident_id} not found.")


# ── State conflicts (→ HTTP 409) ──────────────────────────────────────────────

class ConflictError(AiOpsError):
    pass


class ApprovalAlreadyDecidedError(ConflictError):
    def __init__(self, status: str) -> None:
        super().__init__(f"Approval is already in '{status}' state.")


class ApprovalNotApprovedError(ConflictError):
    def __init__(self, status: str) -> None:
        super().__init__(f"Approval is in '{status}' state, expected 'approved'.")


# ── Domain validation (→ HTTP 422) ────────────────────────────────────────────

class DomainValidationError(AiOpsError):
    pass


class UnknownActionTypeError(DomainValidationError):
    def __init__(self, action_type: str) -> None:
        super().__init__(f"No MCP server registered for action type '{action_type}'.")


# ── Graph / AI engine (→ HTTP 503) ───────────────────────────────────────────

class GraphEngineError(AiOpsError):
    pass


# ── MCP transport/tool (→ HTTP 502) ──────────────────────────────────────────

class MCPError(AiOpsError):
    pass


class UnknownMCPServerError(MCPError):
    def __init__(self, server: str, available: object) -> None:
        super().__init__(
            f"Unknown MCP server '{server}'. Choose from: {sorted(available)}"  # type: ignore[call-overload]
        )


# ── Infrastructure (→ HTTP 500) ───────────────────────────────────────────────

class SchedulerNotRunningError(AiOpsError):
    def __init__(self) -> None:
        super().__init__("Scheduler is not running.")

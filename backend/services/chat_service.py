"""Chat service — orchestrates conversation state and graph invocation."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from backend.constants import GuardrailCategory, GuardrailStatus, MessageRole, RiskLevel
from backend.exceptions import GraphEngineError
from backend.db.repositories import ApprovalRepository, ConversationRepository, IncidentRepository
from backend.services.graph_runner import DefaultGraphRunner, GraphRunner

logger = structlog.get_logger(__name__)

_INTENT_DOMAINS: dict[str, list[str]] = {
    "sales_analysis": ["sales"],
    "inventory_check": ["inventory"],
    "marketing_performance": ["marketing"],
    "support_analysis": ["support"],
    "multi_domain": ["sales", "inventory", "marketing", "support"],
    "unknown": [],
    "action": [],
}


class ChatService:
    """Handle an incoming user chat message end-to-end.

    Args:
        session: An open async SQLAlchemy session.
    """

    def __init__(
        self, session: AsyncSession, graph_runner: GraphRunner | None = None
    ) -> None:
        self._session = session
        self._conv_repo = ConversationRepository(session)
        self._graph_runner: GraphRunner = graph_runner or DefaultGraphRunner()

    async def _create_incidents_from_findings(
        self,
        *,
        conversation_id: uuid.UUID,
        intent_val: str,
        findings: list[dict[str, Any]],
        log_event: str,
    ) -> None:
        """Persist deduplicated incidents from notable findings."""
        notable = [
            finding
            for finding in findings
            if finding.get("severity") in ("critical", "warning")
        ]
        if not notable:
            return

        domains = _INTENT_DOMAINS.get(intent_val, [])
        incident_repo = IncidentRepository(self._session)
        today = date.today()
        created_count = 0

        for finding in notable[:3]:
            already_exists = await incident_repo.exists_for_date_type(
                intent_val,
                today,
            )
            if already_exists:
                continue

            severity = finding.get("severity", "warning")
            root_cause_text = finding.get("root_cause", "")
            root_causes = (
                [{
                    "cause": root_cause_text,
                    "confidence": 0.9 if severity == "critical" else 0.7,
                    "domains": domains,
                }]
                if root_cause_text
                else []
            )
            await incident_repo.create(
                conversation_id=conversation_id,
                incident_date=today,
                incident_type=intent_val,
                title=finding.get("title", "Unnamed issue"),
                summary=finding.get("detail", ""),
                affected_domains=domains,
                root_causes=root_causes,
                affected_products=finding.get("affected_products") or [],
                affected_regions=finding.get("affected_regions") or [],
                confidence=0.9 if severity == "critical" else 0.7,
            )
            created_count += 1

        if created_count:
            logger.info(log_event, count=created_count)

    async def _update_incident_with_actions(
        self,
        *,
        conversation_id: uuid.UUID,
        actions_taken: list[str],
    ) -> None:
        """Backfill the conversation's incident with actions taken by the graph."""
        if not actions_taken:
            return

        try:
            incident_repo = IncidentRepository(self._session)
            incidents = await incident_repo.find_by_conversation(
                conversation_id, limit=1
            )
            if not incidents:
                return

            action_records = [
                {"action_type": a, "tool": a, "server": "", "result": None, "success": True}
                for a in actions_taken
            ]
            outcome = "; ".join(actions_taken)
            await incident_repo.update_after_execution(
                incident=incidents[0],
                actions_taken=action_records,
                outcome_summary=f"Graph executed: {outcome}",
                resolved=True,
            )
        except Exception as exc:
            logger.warning("incident_update_actions_failed", error=str(exc))

    async def _setup_conversation(
        self,
        message: str,
        conversation_id: uuid.UUID | None,
        *,
        log_suffix: str = "",
    ) -> tuple[uuid.UUID, Any, list[dict]]:
        """Create or resume a conversation, add the user message, return history."""
        if conversation_id is None:
            convo: Any = await self._conv_repo.create(
                title=message[:80] if len(message) > 80 else message
            )
            conversation_id = convo.conversation_id
            logger.info("new_conversation" + log_suffix, conversation_id=str(conversation_id))
        else:
            convo = await self._conv_repo.get(conversation_id)
            if convo is None:
                convo = await self._conv_repo.create()
                conversation_id = convo.conversation_id
                logger.warning(
                    "unknown_conversation_id_reset" + log_suffix,
                    requested=str(conversation_id),
                )

        user_msg = await self._conv_repo.add_message(
            conversation_id, role=MessageRole.USER, content=message
        )
        await self._conv_repo.touch(conversation_id)

        convo_with_msgs = await self._conv_repo.get_with_messages(conversation_id)
        conversation_history: list[dict] = []
        if convo_with_msgs and convo_with_msgs.messages:
            for m in convo_with_msgs.messages:
                if str(m.message_id) == str(user_msg.message_id):
                    continue
                if m.role == MessageRole.ASSISTANT and m.structured_response:
                    content = m.structured_response.get("summary", m.content)
                else:
                    content = m.content
                conversation_history.append({"role": m.role, "content": content})

        return conversation_id, user_msg, conversation_history

    async def _persist_graph_result(
        self,
        *,
        conversation_id: uuid.UUID,
        graph_result: dict[str, Any],
        log_suffix: str = "",
    ) -> tuple[dict[str, Any], Any]:
        """Persist approvals, incidents, and assistant message; commit session."""
        response_details = graph_result.get("response_details", {})

        pending_approvals = graph_result.get("pending_approvals", [])
        if pending_approvals:
            approval_repo = ApprovalRepository(self._session)
            enriched_approvals = []
            for a in pending_approvals:
                db_approval = await approval_repo.create_approval(
                    conversation_id=conversation_id,
                    action_type=a.get("tool", "unknown"),
                    target_entities=a.get("arguments", {}),
                    reason=a.get("reason", ""),
                    expected_impact=None,
                    risk_level=a.get("risk_level", RiskLevel.MEDIUM),
                    reversible=bool(a.get("reversible", True)),
                )
                enriched_approvals.append({**dict(a), "approval_id": str(db_approval.approval_id)})
            response_details = dict(response_details)
            response_details["pending_approvals"] = enriched_approvals

        findings = response_details.get("findings", [])
        if findings:
            try:
                await self._create_incidents_from_findings(
                    conversation_id=conversation_id,
                    intent_val=graph_result.get("intent", "unknown"),
                    findings=findings,
                    log_event="incidents_created" + log_suffix,
                )
            except Exception as inc_exc:
                logger.warning("incident_creation_failed" + log_suffix, error=str(inc_exc))

        await self._update_incident_with_actions(
            conversation_id=conversation_id,
            actions_taken=response_details.get("actions_taken", []),
        )

        assistant_msg = await self._conv_repo.add_message(
            conversation_id,
            role=MessageRole.ASSISTANT,
            content=graph_result["response_summary"],
            structured_response=response_details,
        )
        await self._conv_repo.touch(conversation_id)
        await self._session.commit()

        return response_details, assistant_msg

    async def handle(
        self,
        message: str,
        conversation_id: uuid.UUID | None,
    ) -> dict[str, Any]:
        """Process a user message and return a structured investigation result."""
        conversation_id, _, conversation_history = await self._setup_conversation(
            message, conversation_id
        )

        try:
            graph_result = await self._graph_runner.run(
                user_query=message,
                conversation_history=conversation_history,
            )
        except Exception as exc:
            error_msg = str(exc)
            logger.error("graph_error", conversation_id=str(conversation_id), error=error_msg)
            raise GraphEngineError(f"AI-ops engine error: {error_msg}") from exc

        response_details, assistant_msg = await self._persist_graph_result(
            conversation_id=conversation_id,
            graph_result=graph_result,
        )

        logger.info(
            "chat_handled",
            conversation_id=str(conversation_id),
            intent=graph_result["intent"],
        )

        return {
            "conversation_id": conversation_id,
            "message_id":      assistant_msg.message_id,
            "intent":          graph_result["intent"],
            "status":          "completed",
            "response":        response_details,
        }

    async def setup_stream(
        self,
        message: str,
        conversation_id: uuid.UUID | None,
    ) -> dict[str, Any]:
        """Set up conversation state before opening the SSE stream."""
        from langchain_core.messages import AIMessage as _AIMsg
        from langchain_core.messages import HumanMessage as _HMsg

        conversation_id, user_msg, conversation_history = await self._setup_conversation(
            message, conversation_id, log_suffix="_stream"
        )

        lc_messages: list[Any] = []
        for msg in conversation_history[-10:]:
            if msg["role"] == MessageRole.USER:
                lc_messages.append(_HMsg(content=msg["content"]))
            elif msg["role"] == MessageRole.ASSISTANT:
                lc_messages.append(_AIMsg(content=msg["content"]))
        lc_messages.append(_HMsg(content=message))

        initial_state: dict[str, Any] = {
            "messages":               lc_messages,
            "user_query":             message,
            "intent":                 "unknown",
            "tool_results":           [],
            "pending_approvals":      [],
            "needs_write":            False,
            "approved":               False,
            "action_plan_blocker":     None,
            "response_summary":       "",
            "response_details":       {},
            "error":                  None,
            "guardrail_status":       GuardrailStatus.ALLOWED,
            "guardrail_reason":       "",
            "guardrail_category":     GuardrailCategory.IN_SCOPE,
            "memory_matches":         [],
            "domain_plan":            [],
            "domain_findings":        [],
            "iteration_count":        0,
            "reflection_summary":     "",
            "reflection_confidence":  1.0,
            "reflection_tool_hints":  [],
        }

        await self._session.commit()

        return {
            "conversation_id": conversation_id,
            "user_msg_id":     user_msg.message_id,
            "initial_state":   initial_state,
            "message":         message,
        }

    async def finalize_stream(
        self,
        setup: dict[str, Any],
        final_state: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist streamed graph results and return the chat response payload."""
        conversation_id: uuid.UUID = setup["conversation_id"]

        graph_result: dict[str, Any] = {
            "intent":             final_state.get("intent", "unknown"),
            "response_summary":   final_state.get("response_summary", ""),
            "response_details":   final_state.get("response_details", {}),
            "tool_results":       final_state.get("tool_results", []),
            "pending_approvals":  final_state.get("pending_approvals", []),
            "needs_write":        final_state.get("needs_write", False),
            "approved":           final_state.get("approved", False),
            "error":              final_state.get("error"),
            "memory_matches":     final_state.get("memory_matches", []),
        }

        response_details, assistant_msg = await self._persist_graph_result(
            conversation_id=conversation_id,
            graph_result=graph_result,
            log_suffix="_stream",
        )

        logger.info(
            "chat_stream_finalized",
            conversation_id=str(conversation_id),
            intent=graph_result["intent"],
        )

        return {
            "conversation_id": str(conversation_id),
            "message_id":      str(assistant_msg.message_id),
            "intent":          graph_result["intent"],
            "status":          "completed",
            "response":        response_details,
        }

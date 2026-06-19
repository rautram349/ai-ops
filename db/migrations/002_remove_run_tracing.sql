-- =============================================================================
-- Migration: 002_remove_run_tracing.sql
-- Description: Remove local run-trace persistence and decouple approvals/actions.
-- =============================================================================

BEGIN;

DROP VIEW IF EXISTS v_pending_approvals;

DROP TABLE IF EXISTS tool_calls;
DROP TABLE IF EXISTS run_steps;

ALTER TABLE approval_requests DROP COLUMN IF EXISTS run_id;
ALTER TABLE executed_actions DROP COLUMN IF EXISTS run_id;
DROP INDEX IF EXISTS idx_executed_actions_run;

DROP TABLE IF EXISTS runs;

CREATE VIEW v_pending_approvals AS
SELECT
    ar.approval_id,
    ar.conversation_id,
    ar.action_type,
    ar.target_entities,
    ar.reason,
    ar.expected_impact,
    ar.risk_level,
    ar.reversible,
    ar.created_at
FROM approval_requests ar
WHERE ar.status = 'pending'
ORDER BY ar.created_at ASC;

COMMIT;

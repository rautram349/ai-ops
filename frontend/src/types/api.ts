// ─── Intent ───────────────────────────────────────────────────────────────────
export type Intent =
  | "sales_analysis"
  | "inventory_check"
  | "marketing_performance"
  | "support_analysis"
  | "multi_domain"
  | "unknown";

// ─── Chat API ─────────────────────────────────────────────────────────────────
export interface Finding {
  title: string;
  detail: string;
  severity: "info" | "warning" | "critical";
}

export interface RecommendedAction {
  action_type: string;
  reason: string;
  risk_level?: "low" | "medium" | "high";
  reversible?: boolean;
}

export interface PendingApproval {
  tool: string;
  server: string;
  arguments: Record<string, unknown>;
  reason: string;
  approval_id?: string;
  risk_level?: "low" | "medium" | "high";
  reversible?: boolean;
}

export interface AssistantResponse {
  summary: string;
  findings: Finding[];
  recommendations: RecommendedAction[];
  actions_taken: string[];
  pending_approvals?: PendingApproval[];
}

export interface ChatRequest {
  message: string;
  conversation_id: string | null;
}

export interface ChatResponse {
  conversation_id: string;
  message_id: string;
  intent: Intent;
  status: "completed" | "failed";
  response: AssistantResponse;
}

// ─── Conversations ────────────────────────────────────────────────────────────
export interface ConversationSummary {
  conversation_id: string;
  title: string;
  started_at: string;
  last_activity: string;
  status: "active" | "archived";
  message_count: number;
}

export interface ConversationListResponse {
  conversations: ConversationSummary[];
}

export interface Message {
  message_id: string;
  role: "user" | "assistant";
  content: string;
  structured_response: AssistantResponse | null;
  created_at: string;
  intent?: Intent;
}

export interface ConversationDetail {
  conversation_id: string;
  title: string;
  started_at: string;
  last_activity: string;
  status: "active" | "archived";
  messages: Message[];
}

// ─── Approvals ────────────────────────────────────────────────────────────────
export interface ApprovalRequest {
  approval_id: string;
  conversation_id: string;
  action_type: string;
  target_entities: Record<string, unknown>;
  reason: string;
  expected_impact: string | null;
  risk_level: "low" | "medium" | "high";
  reversible: boolean;
  status: "pending" | "approved" | "rejected";
  created_at: string;
  decided_at: string | null;
  decision_note: string | null;
}

export interface ApprovalListResponse {
  approvals: ApprovalRequest[];
}

export interface ApprovalDecision {
  decided_by?: string;
  decision_note?: string;
}

export interface ApprovalResult {
  approval_id: string;
  status: "approved";
  decided_at: string;
}

export interface RejectionResult {
  approval_id: string;
  status: "rejected";
  decided_at: string;
}

export interface ExecutionResult {
  approval_id: string;
  success: boolean;
  result: Record<string, unknown> | null;
  error: string | null;
  executed_at: string;
}

// ─── Incidents ────────────────────────────────────────────────────────────────
export interface IncidentRootCause {
  cause: string;
  confidence: number;
  domains: string[];
}

export interface IncidentActionTaken {
  action_type: string;
  target: string;
  outcome: string;
}

export interface Incident {
  incident_id: string;
  conversation_id: string | null;
  incident_date: string;
  incident_type: string;
  title: string;
  summary: string;
  affected_domains: string[];
  affected_products: string[] | null;
  affected_regions: string[] | null;
  root_causes: IncidentRootCause[];
  actions_taken: IncidentActionTaken[] | null;
  outcome_summary: string | null;
  confidence: number | null;
  resolved: boolean;
  created_at: string;
  resolved_at: string | null;
}

export interface IncidentListResponse {
  incidents: Incident[];
}

// ─── Health ───────────────────────────────────────────────────────────────────
export interface HealthResponse {
  status: "ok";
  timestamp: string;
}

// ─── Optimistic message (local-only before backend responds) ──────────────────
export interface OptimisticMessage extends Omit<
  Message,
  "structured_response"
> {
  structured_response: AssistantResponse | null;
  isOptimistic?: boolean;
  isLoading?: boolean;
  isSystemEvent?: boolean;
  currentNode?: string; // active pipeline node during streaming (e.g. "diagnose")
}



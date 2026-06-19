import { CheckCircle2, Loader2, Sparkles } from "lucide-react";
import type { OptimisticMessage, Intent } from "../../../types/api";
import { IntentBadge } from "./IntentBadge";
import { SummaryCard } from "./SummaryCard";
import { FindingsTabs } from "./FindingsTabs";
import { RecommendationList } from "./RecommendationList";
import { ApprovalBanner } from "./ApprovalBanner";

interface AssistantMessageProps {
  message: OptimisticMessage;
}

export function AssistantMessage({ message }: AssistantMessageProps) {
  if (message.isLoading) {
    const NODE_LABELS: Record<string, string> = {
      route: "Classifying intent?",
      recall: "Searching memory?",
      plan_domains: "Selecting investigation domains?",
      sales_agent: "Analyzing sales data?",
      inventory_agent: "Checking inventory?",
      marketing_agent: "Reviewing campaigns?",
      support_agent: "Analyzing support data?",
      postgres_agent: "Running SQL queries?",
      synthesize: "Correlating findings?",
      reflect: "Evaluating evidence?",
      plan: "Planning actions?",
      execute: "Executing approved actions?",
      respond: "Generating response?",
      respond_unknown: "Generating response?",
      respond_pending: "Preparing approval request?",
    };
    const nodeLabel = message.currentNode
      ? (NODE_LABELS[message.currentNode] ?? "Analyzing?")
      : "Analyzing?";

    return (
      <div className="flex gap-4 animate-fade-in">
        <Avatar />
        <div className="surface-card-lg min-w-0 flex flex-1 items-center gap-3 px-5 py-4">
          <Loader2 size={13} className="animate-spin" style={{ color: "var(--accent)" }} />
          <div className="flex items-center gap-1">
            {[0, 1, 2].map((i) => (
              <span
                key={i}
                className="h-1 w-1 rounded-full animate-pulse"
                style={{ background: "var(--text-ter)", animationDelay: `${i * 200}ms` }}
              />
            ))}
          </div>
          <span style={{ fontSize: "var(--text-base)", color: "var(--text-sec)" }}>{nodeLabel}</span>
        </div>
      </div>
    );
  }

  const resp = message.structured_response;

  if (!resp) {
    return (
      <div className="flex gap-4 animate-fade-in">
        <Avatar />
        <div
          className="surface-card-lg min-w-0 flex-1 text-sm leading-relaxed"
          style={{
            padding: "18px 22px",
            color: "var(--text-sec)",
            whiteSpace: "pre-wrap",
            wordWrap: "break-word",
            overflowWrap: "break-word",
            wordBreak: "break-word",
            overflow: "hidden",
          }}
        >
          {message.content}
        </div>
      </div>
    );
  }

  const hasPendingApprovals = (resp.pending_approvals?.length ?? 0) > 0;
  const hasFindings = (resp.findings?.length ?? 0) > 0;
  const hasRecommendations = (resp.recommendations?.length ?? 0) > 0;
  const hasActions = (resp.actions_taken?.length ?? 0) > 0;

  return (
    <div className="flex gap-4 animate-slide-up">
      <Avatar />

      <div className="surface-card-lg min-w-0 flex-1 overflow-hidden">
        <div className="hairline-x flex items-center justify-between gap-3 px-5 py-4 flex-wrap">
          <div className="flex items-center gap-2 flex-wrap">
            {message.intent && <IntentBadge intent={message.intent as Intent} />}

            {hasActions && (
              <span
                className="pill-badge flex items-center gap-1 border"
                style={{
                  color: "var(--risk-low)",
                  borderColor: "var(--risk-low-border)",
                  background: "transparent",
                }}
              >
                <CheckCircle2 size={10} />
                {resp.actions_taken!.length} action{resp.actions_taken!.length > 1 ? "s" : ""} executed
              </span>
            )}
          </div>
        </div>

        <div
          style={{
            padding: "22px 22px 24px",
            display: "flex",
            flexDirection: "column",
            gap: "24px",
          }}
        >
          <SummaryCard summary={resp.summary} />

          {hasFindings && (
            <>
              <Section label="Findings" />
              <FindingsTabs findings={resp.findings} />
            </>
          )}

          {hasRecommendations && (
            <>
              <Section label="Recommendations" />
              <RecommendationList recommendations={resp.recommendations} />
            </>
          )}

          {hasActions && (
            <>
              <Section label="Actions Executed" />
              <ul className="flex flex-col gap-2">
                {resp.actions_taken!.map((a, i) => (
                  <li key={i} className="flex items-start gap-2.5">
                    <CheckCircle2
                      size={12}
                      className="mt-0.5 shrink-0"
                      style={{ color: "var(--risk-low)" }}
                    />
                    <span
                      style={{
                        fontSize: "var(--text-base)",
                        color: "var(--text-sec)",
                        lineHeight: 1.6,
                      }}
                    >
                      {a}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}

          {hasPendingApprovals && <ApprovalBanner pendingApprovals={resp.pending_approvals!} />}
        </div>
      </div>
    </div>
  );
}

function Avatar() {
  return (
    <div className="mt-1 flex h-10 w-10 shrink-0 items-center justify-center rounded-[var(--radius-sm)] border border-(--border) bg-(--surface-el) text-sm">
      <Sparkles size={14} style={{ color: "var(--accent)" }} />
    </div>
  );
}

function Section({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3">
      <div style={{ height: "1px", width: 28, background: "var(--border)" }} />
      <span className="eyebrow">{label}</span>
      <div style={{ height: "1px", flex: 1, background: "var(--border)" }} />
    </div>
  );
}

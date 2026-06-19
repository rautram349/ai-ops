import { useState } from "react";
import { Link } from "react-router-dom";
import {
  Check,
  X,
  ChevronDown,
  ChevronUp,
  RotateCcw,
  CheckCircle2,
  AlertCircle,
  Package,
  Pause,
  Tag,
  Ticket,
  Siren,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { RiskBadge } from "./RiskBadge";
import { Button } from "../ui/Button";
import type { ApprovalRequest, ExecutionResult } from "../../types/api";

interface ApprovalCardProps {
  approval: ApprovalRequest;
  onApprove: (id: string) => Promise<void>;
  onReject: (id: string, note?: string) => Promise<void>;
  executionResult?: ExecutionResult;
}

const ACTION_ICONS: Record<string, LucideIcon> = {
  restock: Package,
  pause_campaign: Pause,
  apply_discount: Tag,
  create_ticket: Ticket,
  escalate: Siren,
};

function fmtArgs(args: Record<string, unknown>): string {
  return Object.entries(args)
    .map(([k, v]) => `${k}: ${String(v)}`)
    .join("  ·  ");
}

export function ApprovalCard({
  approval,
  onApprove,
  onReject,
  executionResult,
}: ApprovalCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [loadingA, setLoadingA] = useState(false);
  const [loadingR, setLoadingR] = useState(false);
  const [rejectStep, setRejectStep] = useState<"idle" | "confirm">("idle");
  const [rejectNote, setRejectNote] = useState("");

  const isPending = approval.status === "pending";
  const isApproved = approval.status === "approved";
  const Icon = ACTION_ICONS[approval.action_type] ?? Zap;

  const borderStyle = isPending
    ? "var(--border)"
    : isApproved
      ? "var(--risk-low-border)"
      : "var(--risk-high-border)";

  return (
    <div
      className="surface-card overflow-hidden transition-all duration-200"
      style={{
        borderColor: borderStyle,
        opacity: isPending ? 1 : 0.92,
      }}
    >
      <div style={{ padding: "18px 20px" }}>
        <div className="flex items-start gap-4">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[var(--radius-sm)] border border-(--border) bg-(--surface-el)" aria-hidden>
            <Icon size={15} style={{ color: "var(--text-pri)" }} />
          </div>

          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="mb-2 flex items-center gap-2 flex-wrap">
              <RiskBadge risk={approval.risk_level} large />
              <span
                style={{
                  fontSize: "var(--text-sm)",
                  fontWeight: 700,
                  color: "var(--text-pri)",
                  fontFamily: "JetBrains Mono, monospace",
                }}
              >
                {approval.action_type}
              </span>
              {!isPending && (
                <span
                  className="pill-badge border"
                  style={{
                    color: isApproved ? "var(--risk-low)" : "var(--risk-high)",
                    borderColor: isApproved ? "var(--risk-low-border)" : "var(--risk-high-border)",
                    background: "transparent",
                  }}
                >
                  {isApproved ? "APPROVED" : "REJECTED"}
                </span>
              )}
            </div>

            <p
              className="truncate"
              style={{
                fontSize: "var(--text-xs)",
                color: "var(--text-ter)",
                marginBottom: "8px",
                fontFamily: "JetBrains Mono, monospace",
              }}
            >
              {fmtArgs(approval.target_entities)}
            </p>

            <p
              style={{
                fontSize: "var(--text-base)",
                color: "var(--text-sec)",
                lineHeight: 1.6,
                marginBottom: approval.decision_note && !isPending ? "8px" : "10px",
              }}
            >
              {approval.reason}
            </p>

            {!isPending && approval.decision_note && (
              <div
                className="mb-3 rounded-[var(--radius-sm)] border"
                style={{
                  fontSize: "var(--text-sm)",
                  color: isApproved ? "var(--risk-low)" : "var(--risk-high)",
                  borderColor: isApproved ? "var(--risk-low-border)" : "var(--risk-high-border)",
                  background: "transparent",
                  padding: "8px 12px",
                  lineHeight: 1.5,
                }}
              >
                {approval.decision_note}
              </div>
            )}

            <div className="flex items-center gap-3 flex-wrap">
              <span
                className="pill-badge flex items-center gap-1 border"
                style={{
                  color: "var(--text-ter)",
                  borderColor: "var(--border)",
                  background: "transparent",
                }}
              >
                <RotateCcw size={9} />
                {approval.reversible ? "Reversible" : "Irreversible"}
              </span>
              <Link
                to={`/chat/${approval.conversation_id}`}
                className="pill-badge border text-(--accent) transition-colors hover:underline no-underline"
                style={{ borderColor: "var(--accent-border)", background: "transparent" }}
              >
                View conversation →
              </Link>
              {approval.decided_at && (
                <span className="text-meta">{new Date(approval.decided_at).toLocaleString()}</span>
              )}
            </div>
          </div>

          <button
            onClick={() => setExpanded((v) => !v)}
            className="shrink-0 rounded-[var(--radius-sm)] border border-(--border) p-2 text-(--text-ter) transition-colors hover:bg-(--surface-el) hover:text-(--text-sec)"
          >
            {expanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
          </button>
        </div>

        {expanded && (
          <div className="mt-4 animate-fade-in hairline-x" style={{ paddingTop: "16px", borderBottom: "none" }}>
            <p className="eyebrow mb-2">Arguments</p>
            <pre
              className="mono overflow-x-auto rounded-[var(--radius-sm)] border border-(--border) bg-(--surface-el)"
              style={{
                fontSize: "var(--text-xs)",
                color: "var(--text-sec)",
                padding: "14px 16px",
                maxHeight: "150px",
              }}
            >
              {JSON.stringify(approval.target_entities, null, 2)}
            </pre>
            {approval.expected_impact && (
              <div style={{ marginTop: "10px" }}>
                <p className="eyebrow mb-1.5">Expected Impact</p>
                <p style={{ fontSize: "0.78rem", color: "var(--text-sec)" }}>{approval.expected_impact}</p>
              </div>
            )}
          </div>
        )}
      </div>

      {executionResult && isApproved && (
        <div
          className="flex items-start gap-2.5 hairline-x"
          style={{
            padding: "12px 20px",
            borderBottom: "none",
            background: executionResult.success ? "var(--risk-low-soft)" : "var(--risk-high-soft)",
          }}
        >
          {executionResult.success ? (
            <CheckCircle2 size={13} style={{ color: "var(--risk-low)", flexShrink: 0, marginTop: "2px" }} />
          ) : (
            <AlertCircle size={13} style={{ color: "var(--risk-high)", flexShrink: 0, marginTop: "2px" }} />
          )}
          <p
            style={{
              fontSize: "var(--text-sm)",
              color: executionResult.success ? "var(--risk-low)" : "var(--risk-high)",
              lineHeight: 1.5,
            }}
          >
            {executionResult.success
              ? `Executed successfully — ${executionResult.result?.message ?? executionResult.result?.status ?? "action completed"}`
              : `Execution failed: ${executionResult.error}`}
          </p>
        </div>
      )}

      {isPending && (
        <div className="hairline-x" style={{ borderBottom: "none", background: "var(--surface-panel)" }}>
          {rejectStep === "confirm" ? (
            <div style={{ padding: "14px 20px" }}>
              <p
                style={{
                  fontSize: "var(--text-xs)",
                  color: "var(--text-ter)",
                  marginBottom: "8px",
                  fontWeight: 500,
                }}
              >
                Reason for rejection (optional)
              </p>
              <textarea
                value={rejectNote}
                onChange={(e) => setRejectNote(e.target.value)}
                placeholder="e.g. Incorrect quantity, wrong product ID…"
                rows={2}
                style={{
                  width: "100%",
                  resize: "vertical",
                  fontSize: "var(--text-base)",
                  color: "var(--text-pri)",
                  background: "var(--surface-raised)",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--radius-sm)",
                  padding: "10px 12px",
                  outline: "none",
                  fontFamily: "inherit",
                  marginBottom: "12px",
                }}
                autoFocus
              />
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={loadingR}
                  onClick={() => {
                    setRejectStep("idle");
                    setRejectNote("");
                  }}
                >
                  Cancel
                </Button>
                <Button
                  variant="danger"
                  size="sm"
                  loading={loadingR}
                  onClick={async () => {
                    setLoadingR(true);
                    try {
                      await onReject(approval.approval_id, rejectNote || undefined);
                    } finally {
                      setLoadingR(false);
                      setRejectStep("idle");
                      setRejectNote("");
                    }
                  }}
                >
                  <X size={12} />
                  Confirm Reject
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-2.5" style={{ padding: "14px 20px" }}>
              <Button
                variant="danger"
                size="sm"
                disabled={loadingA}
                onClick={() => setRejectStep("confirm")}
              >
                <X size={12} />
                Reject
              </Button>
              <Button
                variant="primary"
                size="sm"
                loading={loadingA}
                disabled={loadingR}
                onClick={async () => {
                  setLoadingA(true);
                  try {
                    await onApprove(approval.approval_id);
                  } finally {
                    setLoadingA(false);
                  }
                }}
              >
                <Check size={12} />
                Approve &amp; Execute
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

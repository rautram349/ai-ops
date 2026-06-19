import { Link } from "react-router-dom";
import { ArrowRight, ShieldAlert } from "lucide-react";
import type { PendingApproval } from "../../../types/api";

export function ApprovalBanner({
  pendingApprovals,
}: {
  pendingApprovals: PendingApproval[];
}) {
  if (!pendingApprovals.length) return null;

  return (
    <div
      className="surface-card flex items-start gap-3.5 overflow-hidden"
      style={{
        padding: "15px 16px",
        boxShadow: "none",
        borderLeft: "4px solid var(--risk-high)",
      }}
    >
      <ShieldAlert
        size={14}
        style={{ color: "var(--risk-high)", flexShrink: 0, marginTop: "2px" }}
      />
      <div style={{ flex: 1, minWidth: 0 }}>
        <p
          style={{
            fontSize: "var(--text-sm)",
            fontWeight: 700,
            color: "var(--text-pri)",
            marginBottom: "4px",
          }}
        >
          {pendingApprovals.length} action{pendingApprovals.length > 1 ? "s" : ""} require approval
        </p>
        <p
          style={{
            fontSize: "var(--text-base)",
            color: "var(--text-sec)",
            lineHeight: 1.55,
          }}
        >
          The agent wants to execute write operations. Review and approve or reject them before they run.
        </p>
      </div>
      <Link
        to="/approvals"
        className="inline-flex items-center gap-1 rounded-[var(--radius-sm)] border border-transparent px-3 py-2 text-(length:--text-xs) font-semibold text-(--text-sec) no-underline transition-all duration-150 hover:bg-(--surface-el) hover:text-(--text-pri)"
      >
        Review in Approvals
        <ArrowRight size={12} />
      </Link>
    </div>
  );
}

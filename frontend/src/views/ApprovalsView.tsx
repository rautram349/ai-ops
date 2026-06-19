import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getApprovals } from "../api/approvals";
import { useApprovalStore } from "../stores/approvalStore";
import { useChatStore } from "../stores/chatStore";
import { ApprovalCard } from "../components/approvals/ApprovalCard";
import { Spinner } from "../components/ui/Spinner";
import { showToast } from "../components/ui/Toast";
import { Button } from "../components/ui/Button";
import { Tabs } from "../components/ui/Tabs";
import { PageHeader } from "../components/ui/PageHeader";
import { CheckSquare, RefreshCw, AlertCircle } from "lucide-react";

type StatusFilter = "pending" | "approved" | "rejected" | "all";

const FILTER_TABS = [
  { label: "Pending", value: "pending" as StatusFilter, dotColor: "var(--risk-high)" },
  { label: "Approved", value: "approved" as StatusFilter, dotColor: "var(--risk-low)" },
  { label: "Rejected", value: "rejected" as StatusFilter, dotColor: "var(--risk-medium)" },
  { label: "All", value: "all" as StatusFilter },
];

export default function ApprovalsView() {
  const [filter, setFilter] = useState<StatusFilter>("pending");
  const navigate = useNavigate();
  const { approve, reject, executionResults } = useApprovalStore();
  const injectSystemMessage = useChatStore((s) => s.injectSystemMessage);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["approvals", filter],
    queryFn: () => getApprovals(filter),
    refetchInterval: 10_000,
  });

  const approvals = data?.approvals ?? [];
  const pendingCount = approvals.filter((a) => a.status === "pending").length;

  const handleApprove = async (id: string) => {
    const approval = approvals.find((a) => a.approval_id === id);
    await approve(id);
    await refetch();
    showToast("Action approved and executed.", "success");

    if (approval?.conversation_id) {
      const execResult = useApprovalStore.getState().executionResults[id];
      const label = approval.action_type.replace(/_/g, " ");
      const content = execResult?.success
        ? `\u2713 ${label} executed successfully`
        : `\u2717 ${label} approved but execution failed: ${execResult?.error ?? "unknown error"}`;
      navigate(`/chat/${approval.conversation_id}`);
      injectSystemMessage(approval.conversation_id, content);
    }
  };

  const handleReject = async (id: string, note?: string) => {
    const approval = approvals.find((a) => a.approval_id === id);
    await reject(id, note);
    await refetch();
    showToast("Action rejected.", "info");

    if (approval?.conversation_id) {
      const label = approval.action_type.replace(/_/g, " ");
      const content = note ? `\u2717 ${label} rejected — ${note}` : `\u2717 ${label} rejected`;
      navigate(`/chat/${approval.conversation_id}`);
      injectSystemMessage(approval.conversation_id, content);
    }
  };

  return (
    <div className="page-shell">
      <div className="page-content-narrow">
        <PageHeader
          icon={<CheckSquare size={15} style={{ color: "var(--accent)" }} />}
          title="Approval Queue"
          subtitle={
            isLoading
              ? "Loading…"
              : pendingCount > 0
                ? `${pendingCount} pending action${pendingCount > 1 ? "s" : ""} require review`
                : "No pending approvals"
          }
          actions={
            <Button variant="secondary" size="sm" onClick={() => refetch()}>
              <RefreshCw size={12} />
              Refresh
            </Button>
          }
        />

        <div style={{ marginTop: "24px", marginBottom: "32px" }}>
          <Tabs tabs={FILTER_TABS} value={filter} onChange={setFilter} className="gap-5" />
        </div>

        {isLoading ? (
          <div className="empty-state-card animate-fade-in">
            <Spinner size="lg" />
            <p style={{ fontSize: "var(--text-base)", color: "var(--text-ter)" }}>Loading approvals…</p>
          </div>
        ) : error ? (
          <div className="page-banner flex items-center gap-3" style={{ borderColor: "var(--risk-high-border)", background: "var(--danger-soft)" }}>
            <AlertCircle size={15} style={{ color: "var(--risk-high)", flexShrink: 0 }} />
            <p style={{ fontSize: "var(--text-base)", color: "var(--text-pri)" }}>
              Failed to load approvals. Check that the backend is running.
            </p>
          </div>
        ) : approvals.length === 0 ? (
          <div className="empty-state-card animate-fade-in">
            <div className="empty-state-icon">
              <CheckSquare size={20} style={{ color: "var(--text-ter)" }} />
            </div>
            <div className="text-center">
              <p style={{ fontSize: "var(--text-md)", fontWeight: 600, color: "var(--text-sec)" }}>All clear</p>
              <p style={{ fontSize: "var(--text-base)", color: "var(--text-ter)", marginTop: "4px" }}>
                No {filter !== "all" ? filter : ""} approvals at the moment.
              </p>
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-4 animate-fade-in">
            {approvals.map((a) => (
              <ApprovalCard
                key={a.approval_id}
                approval={a}
                onApprove={handleApprove}
                onReject={handleReject}
                executionResult={executionResults[a.approval_id]}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

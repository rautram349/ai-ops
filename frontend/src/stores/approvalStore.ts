import { create } from "zustand";
import * as approvalsApi from "../api/approvals";
import type { ApprovalRequest, ExecutionResult } from "../types/api";

interface ApprovalState {
  approvals: ApprovalRequest[];
  pendingCount: number;
  isLoading: boolean;
  error: string | null;
  executionResults: Record<string, ExecutionResult>;

  fetchApprovals(status?: string): Promise<void>;
  approve(approvalId: string, note?: string): Promise<void>;
  reject(approvalId: string, note?: string): Promise<void>;
}

export const useApprovalStore = create<ApprovalState>((set, _get) => ({
  approvals: [],
  pendingCount: 0,
  isLoading: false,
  error: null,
  executionResults: {},

  fetchApprovals: async (status) => {
    set({ isLoading: true, error: null });
    try {
      const data = await approvalsApi.getApprovals(status);
      const pending = data.approvals.filter(
        (a) => a.status === "pending",
      ).length;
      set({
        approvals: data.approvals,
        pendingCount: pending,
        isLoading: false,
      });
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to fetch approvals.";
      set({ error: message, isLoading: false });
    }
  },

  approve: async (approvalId, note) => {
    set({ error: null });
    try {
      await approvalsApi.approve(
        approvalId,
        note ? { decision_note: note } : undefined,
      );
      set((s) => {
        const updated = s.approvals.map((a) =>
          a.approval_id === approvalId
            ? {
                ...a,
                status: "approved" as const,
                decided_at: new Date().toISOString(),
              }
            : a,
        );
        return {
          approvals: updated,
          pendingCount: updated.filter((a) => a.status === "pending").length,
        };
      });

      // Immediately execute the approved action
      try {
        const execResult = await approvalsApi.executeApproval(approvalId);
        set((s) => ({
          executionResults: { ...s.executionResults, [approvalId]: execResult },
        }));
      } catch {
        // Execution errors are captured in executionResults via the API response
        // (the endpoint returns success:false rather than throwing)
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to approve.";
      set({ error: message });
      throw err;
    }
  },

  reject: async (approvalId, note) => {
    set({ error: null });
    try {
      await approvalsApi.reject(
        approvalId,
        note ? { decision_note: note } : undefined,
      );
      set((s) => {
        const updated = s.approvals.map((a) =>
          a.approval_id === approvalId
            ? {
                ...a,
                status: "rejected" as const,
                decided_at: new Date().toISOString(),
              }
            : a,
        );
        return {
          approvals: updated,
          pendingCount: updated.filter((a) => a.status === "pending").length,
        };
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to reject.";
      set({ error: message });
      throw err;
    }
  },
}));

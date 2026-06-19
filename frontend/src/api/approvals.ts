import { get, post } from "./client";
import type {
  ApprovalListResponse,
  ApprovalDecision,
  ApprovalResult,
  RejectionResult,
  ExecutionResult,
} from "../types/api";

export const getApprovals = (status?: string): Promise<ApprovalListResponse> =>
  get<ApprovalListResponse>("/api/approvals", status ? { status } : undefined);

export const approve = (
  id: string,
  body?: ApprovalDecision,
): Promise<ApprovalResult> =>
  post<ApprovalResult>(`/api/approvals/${id}/approve`, body ?? {});

export const reject = (
  id: string,
  body?: ApprovalDecision,
): Promise<RejectionResult> =>
  post<RejectionResult>(`/api/approvals/${id}/reject`, body ?? {});

export const executeApproval = (id: string): Promise<ExecutionResult> =>
  post<ExecutionResult>(`/api/approvals/${id}/execute`, {});

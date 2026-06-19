import { get, post } from "./client";

export interface MonitorRun {
  triggered_at: string;
  status: "running" | "completed" | "error";
  check_date: string | null;
  anomalies_found: number;
  incidents_created: number;
  duration_ms: number | null;
  error: string | null;
  detail: Array<{ incident_type: string; title: string; action: string }>;
}

export interface MonitorStatus {
  last_run: MonitorRun | null;
  next_run_at: string | null;
  interval_minutes: number;
  new_incident_count: number;
}

export const getMonitorStatus = (since?: string): Promise<MonitorStatus> =>
  get<MonitorStatus>("/api/monitor/status", since ? { since } : undefined);

export const getMonitorRuns = (): Promise<MonitorRun[]> =>
  get<MonitorRun[]>("/api/monitor/runs");

export const triggerMonitor = (): Promise<{ status: string }> =>
  post<{ status: string }>("/api/monitor/trigger", {});

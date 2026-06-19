import { create } from "zustand";
import * as monitorApi from "../api/monitor";
import type { MonitorStatus } from "../api/monitor";

const LAST_VIEWED_KEY = "monitor_last_viewed_at";
const POLL_INTERVAL_MS = 60_000;

interface MonitorState {
  status: MonitorStatus | null;
  newIncidentCount: number;
  isLoading: boolean;
  error: string | null;
  lastViewedAt: string | null; // ISO UTC string stored in localStorage

  fetchStatus(): Promise<void>;
  markViewed(): void;
  startPolling(): () => void; // returns cleanup fn
}

function loadLastViewedAt(): string | null {
  try {
    return localStorage.getItem(LAST_VIEWED_KEY);
  } catch {
    return null;
  }
}

function saveLastViewedAt(iso: string): void {
  try {
    localStorage.setItem(LAST_VIEWED_KEY, iso);
  } catch {
    // ignore storage errors
  }
}

export const useMonitorStore = create<MonitorState>((set, get) => ({
  status: null,
  newIncidentCount: 0,
  isLoading: false,
  error: null,
  lastViewedAt: loadLastViewedAt(),

  fetchStatus: async () => {
    const { lastViewedAt } = get();
    set({ isLoading: true, error: null });
    try {
      const data = await monitorApi.getMonitorStatus(lastViewedAt ?? undefined);
      set({
        status: data,
        newIncidentCount: data.new_incident_count,
        isLoading: false,
      });
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to fetch monitor status.";
      set({ error: message, isLoading: false });
    }
  },

  markViewed: () => {
    const now = new Date().toISOString();
    saveLastViewedAt(now);
    set({ lastViewedAt: now, newIncidentCount: 0 });
  },

  startPolling: () => {
    // Fire immediately, then every POLL_INTERVAL_MS
    get().fetchStatus();
    const id = window.setInterval(() => {
      get().fetchStatus();
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(id);
  },
}));

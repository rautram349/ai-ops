import { get, patch } from "./client";
import type { Incident } from "../types/api";

export const getIncidents = async (
  resolved?: boolean,
): Promise<{ incidents: Incident[] }> => {
  const list = await get<Incident[]>(
    "/api/incidents",
    resolved !== undefined ? { resolved: String(resolved) } : undefined,
  );
  return { incidents: list };
};

export const getIncident = (id: string): Promise<Incident> =>
  get<Incident>(`/api/incidents/${id}`);

export const resolveIncident = (
  id: string,
  outcome_summary?: string,
): Promise<Incident> =>
  patch<Incident>(`/api/incidents/${id}/resolve`, {
    outcome_summary: outcome_summary ?? null,
  });

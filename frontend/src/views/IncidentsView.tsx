import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { getIncidents } from "../api/incidents";
import { Spinner } from "../components/ui/Spinner";
import { Tabs } from "../components/ui/Tabs";
import { PageHeader } from "../components/ui/PageHeader";
import { IncidentCard } from "../components/incidents/IncidentCard";
import { AlertTriangle, CheckCircle2, AlertCircle } from "lucide-react";

type ResolvedFilter = "all" | "open" | "resolved";

const FILTER_TABS = [
  { label: "All", value: "all" as ResolvedFilter },
  { label: "Open", value: "open" as ResolvedFilter, dotColor: "var(--risk-high)" },
  {
    label: "Resolved",
    value: "resolved" as ResolvedFilter,
    dotColor: "var(--risk-low)",
  },
];

export default function IncidentsView() {
  const [filter, setFilter] = useState<ResolvedFilter>("all");
  const navigate = useNavigate();

  const { data, isLoading, error } = useQuery({
    queryKey: ["incidents", filter],
    queryFn: () => getIncidents(filter === "all" ? undefined : filter === "resolved"),
    staleTime: 30_000,
    refetchInterval: 60_000,
  });

  const incidents = data?.incidents ?? [];

  return (
    <div className="page-shell">
      <div className="page-content-narrow">
        <PageHeader
          icon={<AlertTriangle size={15} style={{ color: "var(--severity-warning)" }} />}
          iconBg="var(--surface-el)"
          iconBorder="1px solid var(--border)"
          title="Incident History"
          subtitle={isLoading ? "Loading…" : `${incidents.length} incident${incidents.length !== 1 ? "s" : ""}`}
        />

        <div style={{ marginTop: "24px", marginBottom: "32px" }}>
          <Tabs tabs={FILTER_TABS} value={filter} onChange={setFilter} className="gap-5" />
        </div>

        {isLoading ? (
          <div className="empty-state-card animate-fade-in">
            <Spinner size="lg" />
            <p style={{ fontSize: "var(--text-base)", color: "var(--text-ter)" }}>Loading incidents…</p>
          </div>
        ) : error ? (
          <div className="page-banner flex items-center gap-3" style={{ borderColor: "var(--risk-high-border)", background: "var(--danger-soft)" }}>
            <AlertCircle size={15} className="shrink-0" style={{ color: "var(--risk-high)" }} />
            <p style={{ fontSize: "var(--text-base)", color: "var(--text-pri)" }}>
              Failed to load incidents. Check that the backend is running.
            </p>
          </div>
        ) : incidents.length === 0 ? (
          <div className="empty-state-card animate-fade-in">
            <div className="empty-state-icon">
              <CheckCircle2 size={20} style={{ color: "var(--text-ter)" }} />
            </div>
            <div className="text-center">
              <p style={{ fontSize: "var(--text-md)", fontWeight: 600, color: "var(--text-sec)" }}>No incidents</p>
              <p style={{ fontSize: "var(--text-base)", color: "var(--text-ter)", marginTop: "4px" }}>
                No {filter !== "all" ? filter : ""} incidents found.
              </p>
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-4 animate-fade-in">
            {incidents.map((inc, idx) => (
              <IncidentCard
                key={inc.incident_id}
                incident={inc}
                onClick={() => navigate(`/incidents/${inc.incident_id}`)}
                animationDelay={idx * 40}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

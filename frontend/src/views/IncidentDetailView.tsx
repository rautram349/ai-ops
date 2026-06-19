import { useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getIncident, resolveIncident } from "../api/incidents";
import { ConfidenceBar } from "../components/ui/ConfidenceBar";
import { Spinner } from "../components/ui/Spinner";
import { SectionCard } from "../components/ui/SectionCard";
import { Button } from "../components/ui/Button";
import {
  AlertTriangle,
  CheckCircle2,
  ArrowLeft,
  Calendar,
  MessageSquare,
  ShieldCheck,
  AlertCircle,
  ChevronRight,
} from "lucide-react";

const DOMAIN_COLORS: Record<string, string> = {
  sales: "var(--intent-sales)",
  inventory: "var(--intent-inventory)",
  marketing: "var(--intent-marketing)",
  support: "var(--intent-support)",
};

const TYPE_LABELS: Record<string, string> = {
  sales_analysis: "Sales",
  inventory_check: "Inventory",
  marketing_performance: "Marketing",
  support_analysis: "Support",
  multi_domain: "Multi-Domain",
  unknown: "Unknown",
};

function Chip({ label, color }: { label: string; color?: string }) {
  return (
    <span
      className="pill-badge border font-mono font-semibold"
      style={{
        color: color ?? "var(--text-sec)",
        background: "transparent",
        borderColor: color ? `${color}40` : "var(--border)",
      }}
    >
      {label}
    </span>
  );
}

function DetailGroup({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <p className="eyebrow mb-2">{label}</p>
      {children}
    </div>
  );
}

export default function IncidentDetailView() {
  const { incidentId } = useParams<{ incidentId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [resolveOpen, setResolveOpen] = useState(false);
  const [outcomeNote, setOutcomeNote] = useState("");
  const [resolving, setResolving] = useState(false);
  const [resolveError, setResolveError] = useState<string | null>(null);

  const {
    data: incident,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["incident", incidentId],
    queryFn: () => getIncident(incidentId!),
    enabled: !!incidentId,
    staleTime: 30_000,
  });

  const handleResolve = async () => {
    if (!incidentId) return;
    setResolving(true);
    setResolveError(null);
    try {
      await resolveIncident(incidentId, outcomeNote || undefined);
      await queryClient.invalidateQueries({
        queryKey: ["incident", incidentId],
      });
      await queryClient.invalidateQueries({ queryKey: ["incidents"] });
      setResolveOpen(false);
      setOutcomeNote("");
    } catch (err) {
      setResolveError(
        err instanceof Error ? err.message : "Failed to resolve.",
      );
    } finally {
      setResolving(false);
    }
  };

  if (isLoading) {
    return (
      <div className="page-shell">
        <div className="page-content-narrow">
          <div className="empty-state-card">
            <Spinner size="lg" />
            <p className="text-(length:--text-base) text-(--text-ter)">
              Loading incident details…
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (error || !incident) {
    return (
      <div className="page-shell">
        <div className="page-content-narrow">
          <div className="empty-state-card">
            <div className="empty-state-icon">
              <AlertCircle size={24} style={{ color: "var(--risk-high)" }} />
            </div>
            <p className="text-(length:--text-md) font-semibold text-(--text-pri)">
              Incident not found
            </p>
            <p className="text-(length:--text-base) text-(--text-sec)">
              The incident could not be loaded or no longer exists.
            </p>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => navigate("/incidents")}
            >
              Back to incidents
            </Button>
          </div>
        </div>
      </div>
    );
  }

  const isResolved = incident.resolved;
  const hasProducts = (incident.affected_products ?? []).length > 0;
  const hasRegions = (incident.affected_regions ?? []).length > 0;
  const hasRootCauses = (incident.root_causes ?? []).length > 0;
  const hasActionsTaken = (incident.actions_taken ?? []).length > 0;

  return (
    <div className="page-shell">
      <div className="page-content-narrow section-stack">
        <div className="mb-2 flex items-center gap-2">
          <Link
            to="/incidents"
            className="pill-badge flex items-center gap-1.5 border rounded-[var(--radius-sm)] no-underline text-(--text-sec) transition-all duration-150 hover:bg-(--surface-el) hover:text-(--text-pri)"
            style={{ borderColor: "var(--border)", background: "transparent" }}
          >
            <ArrowLeft size={12} />
            Incidents
          </Link>
          <ChevronRight size={12} style={{ color: "var(--text-ter)" }} />
          <span
            className="text-meta"
            style={{
              maxWidth: "28rem",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {incident.title}
          </span>
        </div>

        <div
          className="surface-card-lg"
          style={{
            padding: "24px 26px",
            borderLeft: `4px solid ${isResolved ? "var(--risk-low)" : "var(--severity-warning)"}`,
          }}
        >
          <div className="flex items-start justify-between gap-4">
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="mb-3 flex items-center gap-2 flex-wrap">
                <span
                  className="pill-badge flex items-center gap-1.5 border font-mono font-semibold"
                  style={{
                    color: "var(--text-ter)",
                    background: "transparent",
                    borderColor: "var(--border)",
                  }}
                >
                  <Calendar size={10} />
                  {incident.incident_date}
                </span>

                <span
                  className="pill-badge capitalize border font-bold"
                  style={{
                    letterSpacing: "0.04em",
                    color: "var(--accent)",
                    background: "transparent",
                    borderColor: "var(--accent-border)",
                  }}
                >
                  {TYPE_LABELS[incident.incident_type] ?? incident.incident_type}
                </span>

                <span
                  className="pill-badge flex items-center gap-1 border font-bold"
                  style={{
                    color: isResolved ? "var(--risk-low)" : "var(--risk-high)",
                    background: "transparent",
                    borderColor: isResolved
                      ? "var(--risk-low-border)"
                      : "var(--risk-high-border)",
                  }}
                >
                  {isResolved ? (
                    <CheckCircle2 size={10} />
                  ) : (
                    <AlertTriangle size={10} />
                  )}
                  {isResolved ? "Resolved" : "Open"}
                </span>
              </div>

              <h1 className="heading-page mb-1">{incident.title}</h1>

              {incident.resolved_at && (
                <p className="text-meta">
                  Resolved at {new Date(incident.resolved_at).toLocaleString()}
                </p>
              )}
            </div>
          </div>
        </div>

        <div className="section-stack">
          <SectionCard elevated title="Summary">
            <p
              style={{
                fontSize: "var(--text-base)",
                color: "var(--text-sec)",
                lineHeight: 1.75,
              }}
            >
              {incident.summary || "No summary available."}
            </p>
          </SectionCard>

          <SectionCard elevated title="Details">
            <div className="flex flex-col gap-5">
              {incident.confidence != null && (
                <DetailGroup label="Diagnosis Confidence">
                  <div className="flex items-center gap-3">
                    <div style={{ flex: 1 }}>
                      <ConfidenceBar value={incident.confidence} />
                    </div>
                    <span
                      style={{
                        fontSize: "var(--text-sm)",
                        fontWeight: 700,
                        color: "var(--text-pri)",
                        fontFamily: "JetBrains Mono, monospace",
                        minWidth: "2.5rem",
                        textAlign: "right",
                      }}
                    >
                      {Math.round(incident.confidence * 100)}%
                    </span>
                  </div>
                </DetailGroup>
              )}

              {incident.affected_domains.length > 0 && (
                <DetailGroup label="Affected Domains">
                  <div className="flex flex-wrap gap-2">
                    {incident.affected_domains.map((d) => (
                      <Chip key={d} label={d} color={DOMAIN_COLORS[d]} />
                    ))}
                  </div>
                </DetailGroup>
              )}

              {hasProducts && (
                <DetailGroup label="Affected Products">
                  <div className="flex flex-wrap gap-2">
                    {incident.affected_products!.map((p) => (
                      <Chip key={p} label={p} />
                    ))}
                  </div>
                </DetailGroup>
              )}

              {hasRegions && (
                <DetailGroup label="Affected Regions">
                  <div className="flex flex-wrap gap-2">
                    {incident.affected_regions!.map((r) => (
                      <Chip key={r} label={r} />
                    ))}
                  </div>
                </DetailGroup>
              )}
            </div>
          </SectionCard>

          {hasRootCauses && (
            <SectionCard elevated title="Root Causes">
              <div className="flex flex-col gap-3">
                {incident.root_causes.map((rc, i) => (
                  <div
                    key={i}
                    className="surface-card flex items-start gap-3"
                    style={{
                      padding: "14px 16px",
                      borderLeft: "2px solid var(--accent)",
                    }}
                  >
                    <ShieldCheck
                      size={14}
                      style={{
                        color: "var(--accent)",
                        flexShrink: 0,
                        marginTop: "1px",
                      }}
                    />
                    <div style={{ flex: 1 }}>
                      <p
                        style={{
                          fontSize: "var(--text-base)",
                          color: "var(--text-pri)",
                          lineHeight: 1.5,
                        }}
                      >
                        {rc.cause}
                      </p>
                      {rc.confidence != null && (
                        <p
                          className="text-meta"
                          style={{ marginTop: "4px", fontFamily: "JetBrains Mono, monospace" }}
                        >
                          {Math.round(rc.confidence * 100)}% confidence
                          {rc.domains?.length > 0 && ` · ${rc.domains.join(", ")}`}
                        </p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </SectionCard>
          )}

          {hasActionsTaken && (
            <SectionCard elevated title="Actions Taken">
              <div className="flex flex-col gap-2">
                {incident.actions_taken!.map((a, i) => (
                  <div
                    key={i}
                    className="surface-card flex items-start gap-3"
                    style={{
                      padding: "12px 14px",
                      borderLeft: "2px solid var(--risk-low)",
                    }}
                  >
                    <CheckCircle2
                      size={13}
                      style={{
                        color: "var(--risk-low)",
                        flexShrink: 0,
                        marginTop: "2px",
                      }}
                    />
                    <div>
                      <p
                        style={{
                          fontSize: "var(--text-base)",
                          fontWeight: 600,
                          color: "var(--text-pri)",
                        }}
                      >
                        {a.action_type}
                        {a.target ? ` — ${a.target}` : ""}
                      </p>
                      {a.outcome && (
                        <p
                          style={{
                            fontSize: "var(--text-sm)",
                            color: "var(--text-sec)",
                            marginTop: "2px",
                          }}
                        >
                          {a.outcome}
                        </p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </SectionCard>
          )}

          {isResolved && incident.outcome_summary && (
            <SectionCard elevated title="Outcome">
              <p
                style={{
                  fontSize: "var(--text-base)",
                  color: "var(--text-sec)",
                  lineHeight: 1.75,
                }}
              >
                {incident.outcome_summary}
              </p>
            </SectionCard>
          )}

          <div className="surface-card flex items-center justify-between flex-wrap gap-3 p-5">
            {incident.conversation_id ? (
              <Link
                to={`/chat/${incident.conversation_id}`}
                className="pill-badge flex items-center gap-2 border font-medium text-(--accent) no-underline transition-all duration-150 hover:bg-(--surface-el)"
                style={{
                  borderColor: "var(--accent-border)",
                  background: "transparent",
                }}
              >
                <MessageSquare size={13} />
                View conversation
              </Link>
            ) : (
              <span />
            )}

            {!isResolved && (
              <div
                className="flex flex-col items-end gap-2"
                style={{ flex: 1, minWidth: 0 }}
              >
                {!resolveOpen ? (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => setResolveOpen(true)}
                    className="text-(--risk-low)"
                    style={{
                      border: "1px solid var(--risk-low-border)",
                      background: "transparent",
                    }}
                  >
                    <CheckCircle2 size={13} />
                    Mark as Resolved
                  </Button>
                ) : (
                  <div
                    className="flex w-full flex-col gap-2"
                    style={{ maxWidth: "28rem" }}
                  >
                    <textarea
                      value={outcomeNote}
                      onChange={(e) => setOutcomeNote(e.target.value)}
                      placeholder="How was this resolved? (optional)"
                      rows={2}
                      style={{
                        width: "100%",
                        fontSize: "var(--text-base)",
                        color: "var(--text-pri)",
                        background: "var(--surface-raised)",
                        border: "1px solid var(--border-h)",
                        borderRadius: "var(--radius-sm)",
                        padding: "10px 12px",
                        resize: "vertical",
                        outline: "none",
                      }}
                    />
                    {resolveError && (
                      <p
                        style={{
                          fontSize: "0.72rem",
                          color: "var(--risk-high)",
                        }}
                      >
                        {resolveError}
                      </p>
                    )}
                    <div className="flex items-center justify-end gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setResolveOpen(false);
                          setOutcomeNote("");
                          setResolveError(null);
                        }}
                      >
                        Cancel
                      </Button>
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={handleResolve}
                        loading={resolving}
                        style={{
                          color: "var(--risk-low)",
                          border: "1px solid var(--risk-low-border)",
                          background: "transparent",
                        }}
                      >
                        Confirm Resolve
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

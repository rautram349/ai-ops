import { Link } from "react-router-dom";
import { AlertTriangle, CheckCircle2, Calendar, Clock } from "lucide-react";
import { ConfidenceBar } from "../ui/ConfidenceBar";
import { formatRelative } from "../../lib/format";
import type { Incident } from "../../types/api";

const DOMAIN_COLORS: Record<string, string> = {
  sales: "var(--intent-sales)",
  inventory: "var(--intent-inventory)",
  marketing: "var(--intent-marketing)",
  support: "var(--intent-support)",
};

interface IncidentCardProps {
  incident: Incident;
  onClick: () => void;
  animationDelay?: number;
}

export function IncidentCard({ incident: inc, onClick, animationDelay }: IncidentCardProps) {
  return (
    <div
      className="surface-card card-hover cursor-pointer overflow-hidden transition-colors duration-200"
      style={{
        padding: "20px 22px",
        borderLeft: `4px solid ${inc.resolved ? "var(--risk-low)" : "var(--severity-warning)"}`,
        animationDelay: animationDelay !== undefined ? `${animationDelay}ms` : undefined,
      }}
      onClick={onClick}
    >
      <div className="mb-3 flex items-start gap-3">
        <div
          className="pill-badge flex items-center gap-1.5 shrink-0 border font-mono font-semibold"
          style={{
            color: "var(--text-ter)",
            background: "transparent",
            borderColor: "var(--border)",
          }}
        >
          <Calendar size={10} />
          {inc.incident_date}
        </div>

        <div className="min-w-0 flex-1">
          <p
            className="mb-1"
            style={{
              fontSize: "var(--text-md)",
              fontWeight: 700,
              color: "var(--text-pri)",
              lineHeight: 1.3,
              letterSpacing: "-0.01em",
            }}
          >
            {inc.title}
          </p>
          <p className="mb-1 flex items-center gap-1 text-meta">
            <Clock size={10} />
            {formatRelative(inc.created_at)}
          </p>
          <p className="line-clamp-2" style={{ fontSize: "var(--text-base)", color: "var(--text-sec)", lineHeight: 1.6 }}>
            {inc.summary}
          </p>
        </div>

        {!inc.conversation_id && (
          <span
            className="pill-badge shrink-0 border font-bold uppercase"
            style={{
              color: "var(--accent)",
              background: "transparent",
              borderColor: "var(--accent-border)",
              letterSpacing: "0.04em",
            }}
          >
            Auto-detected
          </span>
        )}

        <span
          className="pill-badge flex items-center gap-1 shrink-0 border font-bold"
          style={{
            color: inc.resolved ? "var(--risk-low)" : "var(--risk-high)",
            background: "transparent",
            borderColor: inc.resolved ? "var(--risk-low-border)" : "var(--risk-high-border)",
          }}
        >
          {inc.resolved ? <CheckCircle2 size={10} /> : <AlertTriangle size={10} />}
          {inc.resolved ? "Resolved" : "Open"}
        </span>
      </div>

      {inc.affected_domains.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-1.5">
          {inc.affected_domains.map((d) => (
            <span
              key={d}
              className="pill-badge border capitalize font-semibold"
              style={{
                color: DOMAIN_COLORS[d] ?? "var(--text-sec)",
                background: "transparent",
                borderColor: `${DOMAIN_COLORS[d] ?? "var(--border)"}40`,
              }}
            >
              {d}
            </span>
          ))}
        </div>
      )}

      <div className="flex items-center gap-4">
        <div className="flex-1">
          <p className="eyebrow mb-1">Confidence</p>
          <ConfidenceBar value={inc.confidence ?? 0} />
        </div>
        {inc.conversation_id && (
          <Link
            to={`/chat/${inc.conversation_id}`}
            onClick={(e) => e.stopPropagation()}
            className="pill-badge shrink-0 border font-medium text-(--accent) hover:underline transition-colors no-underline"
            style={{ borderColor: "var(--accent-border)", background: "transparent" }}
          >
            View conversation →
          </Link>
        )}
      </div>
    </div>
  );
}

import type { LucideIcon } from "lucide-react";
import { AlertOctagon, AlertTriangle, Info } from "lucide-react";
import type { Finding } from "../../../types/api";

const SEV: Record<string, { Icon: LucideIcon; color: string; label: string }> = {
  info: { Icon: Info, color: "var(--severity-info)", label: "Info" },
  warning: {
    Icon: AlertTriangle,
    color: "var(--severity-warning)",
    label: "Warning",
  },
  critical: {
    Icon: AlertOctagon,
    color: "var(--severity-critical)",
    label: "Critical",
  },
};

export function FindingCard({ finding }: { finding: Finding }) {
  const meta = SEV[finding.severity] ?? SEV.info;
  const Icon = meta.Icon;

  return (
    <div
      className="surface-card flex gap-4 overflow-hidden"
      style={{ padding: "15px 16px", borderLeft: `2px solid ${meta.color}` }}
    >
      <div
        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[var(--radius-sm)] border bg-(--surface-el)"
        style={{ borderColor: "var(--border)" }}
        aria-hidden
      >
        <Icon size={14} style={{ color: meta.color }} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="mb-1.5 flex items-center gap-2 flex-wrap hairline-x pb-2">
          <p
            style={{
              fontSize: "var(--text-base)",
              fontWeight: 700,
              color: "var(--text-pri)",
              lineHeight: 1.3,
            }}
          >
            {finding.title}
          </p>
          <span
            className="pill-badge border"
            style={{
              color: meta.color,
              borderColor: `${meta.color}35`,
              background: "transparent",
            }}
          >
            {meta.label}
          </span>
        </div>
        <p
          style={{
            fontSize: "var(--text-base)",
            color: "var(--text-sec)",
            lineHeight: 1.65,
            paddingTop: "10px",
          }}
        >
          {finding.detail}
        </p>
      </div>
    </div>
  );
}

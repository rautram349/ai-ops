import type { LucideIcon } from "lucide-react";
import { BellRing, Package, Tag, Undo2, Zap } from "lucide-react";
import type { RecommendedAction } from "../../../types/api";

const RISK_META: Record<string, { color: string; label: string }> = {
  low: { color: "var(--risk-low)", label: "Low" },
  medium: { color: "var(--risk-medium)", label: "Med" },
  high: { color: "var(--risk-high)", label: "High" },
};

const ACTION_ICONS: Record<string, LucideIcon> = {
  restock: Package,
  pause_campaign: BellRing,
  apply_discount: Tag,
  create_ticket: BellRing,
  escalate: BellRing,
  update_pricing: Zap,
};

export function ActionCard({ action }: { action: RecommendedAction }) {
  const risk = RISK_META[action.risk_level ?? "low"];
  const Icon = ACTION_ICONS[action.action_type] ?? Zap;

  return (
    <div
      className="surface-card card-hover flex items-start gap-4 transition-all duration-150 hover:border-(--border-h)"
      style={{ padding: "15px 16px" }}
    >
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[var(--radius-sm)] border border-(--border) bg-(--surface-el)">
        <Icon size={14} style={{ color: "var(--text-pri)" }} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="mb-1.5 flex items-center gap-2 flex-wrap">
          <span
            style={{
              fontSize: "var(--text-sm)",
              fontWeight: 700,
              color: "var(--text-pri)",
              fontFamily: "JetBrains Mono, monospace",
            }}
          >
            {action.action_type}
          </span>
          {action.risk_level && (
            <span
              className="pill-badge border"
              style={{
                color: risk.color,
                borderColor: `${risk.color}35`,
                background: "transparent",
              }}
            >
              {risk.label} Risk
            </span>
          )}
          {action.reversible !== undefined && (
            <span
              className="pill-badge border flex items-center gap-1"
              style={{
                color: "var(--text-ter)",
                borderColor: "var(--border)",
                background: "transparent",
              }}
            >
              <Undo2 size={10} />
              {action.reversible ? "Reversible" : "Irreversible"}
            </span>
          )}
        </div>
        <p style={{ fontSize: "var(--text-base)", color: "var(--text-sec)", lineHeight: 1.65 }}>{action.reason}</p>
      </div>
    </div>
  );
}

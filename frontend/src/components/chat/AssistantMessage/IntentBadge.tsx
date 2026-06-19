import type { LucideIcon } from "lucide-react";
import {
  Headphones,
  Megaphone,
  MessageCircle,
  Package,
  Shuffle,
  TrendingDown,
} from "lucide-react";
import type { Intent } from "../../../types/api";

const INTENT_META: Record<Intent, { label: string; color: string; icon: LucideIcon }> = {
  sales_analysis: { label: "Sales", color: "var(--intent-sales)", icon: TrendingDown },
  inventory_check: { label: "Inventory", color: "var(--intent-inventory)", icon: Package },
  marketing_performance: { label: "Marketing", color: "var(--intent-marketing)", icon: Megaphone },
  support_analysis: { label: "Support", color: "var(--intent-support)", icon: Headphones },
  multi_domain: { label: "Multi-Domain", color: "var(--intent-multi)", icon: Shuffle },
  unknown: { label: "General", color: "var(--intent-unknown)", icon: MessageCircle },
};

export function IntentBadge({ intent }: { intent: Intent }) {
  const meta = INTENT_META[intent] ?? INTENT_META.unknown;
  const Icon = meta.icon;

  return (
    <span
      className="pill-badge inline-flex items-center gap-1.5 border font-semibold"
      style={{
        color: meta.color,
        borderColor: `${meta.color}40`,
        backgroundColor: "transparent",
        letterSpacing: "0.02em",
      }}
    >
      <Icon size={12} />
      {meta.label}
    </span>
  );
}

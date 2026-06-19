import { AlertTriangle, CheckCircle2, Info } from "lucide-react";

type Risk = "low" | "medium" | "high";

const CONFIG: Record<
  Risk,
  { label: string; color: string; Icon: typeof CheckCircle2; filled?: boolean }
> = {
  low: {
    label: "Low",
    color: "var(--risk-low)",
    Icon: CheckCircle2,
  },
  medium: {
    label: "Medium",
    color: "var(--risk-medium)",
    Icon: Info,
  },
  high: {
    label: "High",
    color: "var(--risk-high)",
    Icon: AlertTriangle,
    filled: true,
  },
};

export function RiskBadge({
  risk,
  large = false,
}: {
  risk: Risk;
  large?: boolean;
}) {
  const { label, color, Icon, filled } = CONFIG[risk];

  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full font-bold uppercase"
      style={{
        color,
        background: filled ? `${color}14` : "transparent",
        border: `1px solid ${color}30`,
        padding: large ? "4px 10px" : "2px 8px",
        fontSize: large ? "0.72rem" : "0.62rem",
        letterSpacing: "0.05em",
      }}
    >
      <Icon size={large ? 12 : 10} />
      {label}
    </span>
  );
}

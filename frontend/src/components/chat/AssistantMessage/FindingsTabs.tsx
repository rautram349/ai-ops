import { useState } from "react";
import type { Finding } from "../../../types/api";
import { FindingCard } from "./FindingCard";
import { Tabs } from "../../ui/Tabs";
import type { TabItem } from "../../ui/Tabs";

interface FindingsTabsProps {
  findings: Finding[];
}

const SEV_ORDER = { critical: 0, warning: 1, info: 2 };
const SEV_COLOR: Record<string, string> = {
  all: "var(--text-sec)",
  critical: "var(--severity-critical)",
  warning: "var(--severity-warning)",
  info: "var(--severity-info)",
};

type SevFilter = "all" | "critical" | "warning" | "info";

export function FindingsTabs({ findings }: FindingsTabsProps) {
  const [active, setActive] = useState<SevFilter>("all");

  if (!findings.length) return null;

  const counts: Record<SevFilter, number> = {
    all: findings.length,
    critical: findings.filter((f) => f.severity === "critical").length,
    warning: findings.filter((f) => f.severity === "warning").length,
    info: findings.filter((f) => f.severity === "info").length,
  };

  const visibleTabs = (["all", "critical", "warning", "info"] as const).filter(
    (t) => t === "all" || counts[t] > 0,
  );

  const tabItems: TabItem<SevFilter>[] = visibleTabs.map((t) => ({
    value: t,
    label: t === "all" ? "All" : t.charAt(0).toUpperCase() + t.slice(1),
    count: counts[t],
    dotColor: t === "all" ? "var(--text-ter)" : SEV_COLOR[t],
    activeColor: SEV_COLOR[t],
  }));

  const displayed = (
    active === "all" ? [...findings] : findings.filter((f) => f.severity === active)
  ).sort((a, b) => SEV_ORDER[a.severity] - SEV_ORDER[b.severity]);

  return (
    <div>
      <Tabs tabs={tabItems} value={active} onChange={setActive} className="mb-4" />
      <div className="flex flex-col gap-3">
        {displayed.map((f, i) => (
          <FindingCard key={i} finding={f} />
        ))}
      </div>
    </div>
  );
}

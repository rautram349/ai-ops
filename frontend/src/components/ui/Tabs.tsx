import type { KeyboardEvent } from "react";

export interface TabItem<T extends string> {
  value: T;
  label: string;
  count?: number;
  dotColor?: string;
  activeColor?: string;
}

interface TabsProps<T extends string> {
  tabs: TabItem<T>[];
  value: T;
  onChange: (value: T) => void;
  className?: string;
}

export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
  className = "",
}: TabsProps<T>) {
  function handleKeyDown(e: KeyboardEvent<HTMLButtonElement>, idx: number) {
    let next = idx;
    if (e.key === "ArrowRight") next = (idx + 1) % tabs.length;
    else if (e.key === "ArrowLeft") next = (idx - 1 + tabs.length) % tabs.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = tabs.length - 1;
    else return;

    e.preventDefault();
    onChange(tabs[next].value);
    const tabEl = document.getElementById(`tab-${tabs[next].value}`);
    tabEl?.focus();
  }

  return (
    <div
      role="tablist"
      aria-label="Filter options"
      className={["flex items-center flex-wrap gap-5 border-b border-(--border)", className].join(" ")}
    >
      {tabs.map((tab, idx) => {
        const isActive = value === tab.value;
        const accentColor = tab.activeColor ?? "var(--accent)";

        return (
          <button
            key={tab.value}
            role="tab"
            id={`tab-${tab.value}`}
            aria-selected={isActive}
            aria-controls={`tabpanel-${tab.value}`}
            tabIndex={isActive ? 0 : -1}
            onClick={() => onChange(tab.value)}
            onKeyDown={(e) => handleKeyDown(e, idx)}
            className={[
              "inline-flex items-center gap-1.5 border-b bg-transparent pb-3 text-(length:--text-sm) font-semibold cursor-pointer transition-colors duration-150",
              "focus-visible:outline-2 focus-visible:outline-(--accent) focus-visible:outline-offset-2",
              isActive
                ? "text-(--text-pri)"
                : "text-(--text-sec) border-transparent hover:text-(--text-pri)",
            ].join(" ")}
            style={{ borderBottomColor: isActive ? accentColor : "transparent" }}
          >
            {tab.dotColor && (
              <span
                className="h-1.5 w-1.5 rounded-full shrink-0"
                style={{ background: tab.dotColor }}
                aria-hidden="true"
              />
            )}
            {tab.label}
            {tab.count !== undefined && (
              <span
                className="inline-flex h-4.5 min-w-4.5 items-center justify-center rounded-full border px-1.5 font-bold leading-none"
                style={{
                  fontSize: "var(--text-2xs)",
                  color: isActive ? accentColor : "var(--text-sec)",
                  borderColor: isActive ? accentColor : "var(--border)",
                  background: "transparent",
                }}
              >
                {tab.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

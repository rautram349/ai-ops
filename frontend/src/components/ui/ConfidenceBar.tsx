interface ConfidenceBarProps {
  value: number;
  className?: string;
}

export function ConfidenceBar({ value, className = "" }: ConfidenceBarProps) {
  const pct = Math.round(Math.min(Math.max(value, 0), 1) * 100);

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <div className="h-1 w-full flex-1 overflow-hidden rounded-full bg-(--surface-el)">
        <div
          className="h-full rounded-full bg-(--accent) transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-8 text-right font-mono text-xs text-(--text-sec)">
        {pct}%
      </span>
    </div>
  );
}

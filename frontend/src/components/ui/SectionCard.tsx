import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ExternalLink } from "lucide-react";

interface SectionCardProps {
  title: string;
  viewAllHref?: string;
  viewAllLabel?: string;
  children: ReactNode;
  loading?: boolean;
  elevated?: boolean;
  noPad?: boolean;
  minHeight?: number;
  className?: string;
  headerActions?: ReactNode;
}

function LoadingRows() {
  return (
    <div className="flex flex-col gap-3 p-5">
      {[80, 65, 72, 55].map((w) => (
        <div
          key={w}
          className="skeleton h-3 rounded"
          style={{ width: `${w}%` }}
        />
      ))}
    </div>
  );
}

export function SectionCard({
  title,
  viewAllHref,
  viewAllLabel = "View all",
  children,
  loading = false,
  elevated = false,
  noPad = false,
  minHeight,
  className = "",
  headerActions,
}: SectionCardProps) {
  return (
    <div
      className={[
        elevated ? "surface-card-lg" : "surface-card",
        "overflow-hidden flex flex-col",
        className,
      ].join(" ")}
      style={minHeight ? { minHeight } : undefined}
    >
      <div className="hairline-x flex items-center justify-between gap-3 px-5 py-4">
        <p className="eyebrow">{title}</p>
        <div className="flex items-center gap-2">
          {headerActions}
          {viewAllHref && (
            <Link
              to={viewAllHref}
              className="inline-flex items-center gap-1 text-(--accent) hover:underline transition-colors"
              style={{ fontSize: "var(--text-xs)", fontWeight: 500 }}
            >
              {viewAllLabel}
              <ExternalLink size={10} />
            </Link>
          )}
        </div>
      </div>

      <div className="flex-1" style={noPad ? undefined : { padding: "18px 20px 20px" }}>
        {loading ? <LoadingRows /> : children}
      </div>
    </div>
  );
}

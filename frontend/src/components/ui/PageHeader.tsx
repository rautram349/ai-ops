import type { CSSProperties, ReactNode } from "react";

interface PageHeaderProps {
  icon: ReactNode;
  iconBg?: string;
  iconBorder?: string;
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  className?: string;
}

export function PageHeader({
  icon,
  iconBg,
  iconBorder,
  title,
  subtitle,
  actions,
  className = "",
}: PageHeaderProps) {
  const iconStyle: CSSProperties = {
    background: iconBg ?? "var(--surface-el)",
    border: iconBorder ?? "1px solid var(--border)",
  };

  return (
    <div
      className={[
        "mb-8 flex flex-col gap-4 md:flex-row md:items-start md:justify-between",
        className,
      ].join(" ")}
    >
      <div className="flex min-w-0 items-start gap-4">
        <div
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[var(--radius-md)]"
          style={iconStyle}
        >
          {icon}
        </div>
        <div className="min-w-0">
          <h1 className="heading-page truncate">{title}</h1>
          {subtitle && (
            <p
              className="mt-1 leading-relaxed text-(--text-sec)"
              style={{ fontSize: "var(--text-sm)" }}
            >
              {subtitle}
            </p>
          )}
        </div>
      </div>
      {actions && <div className="shrink-0 self-start md:self-auto">{actions}</div>}
    </div>
  );
}

import { type HTMLAttributes } from "react";

type BadgeVariant =
  | "default"
  | "info"
  | "warning"
  | "critical"
  | "success"
  | "muted"
  | "accent";

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
  dot?: boolean;
}

const styles: Record<BadgeVariant, string> = {
  default: "border-(--border) text-(--text-sec) bg-transparent",
  info: "border-(--severity-info)/35 text-(--severity-info) bg-transparent",
  warning:
    "border-(--severity-warning)/35 text-(--severity-warning) bg-transparent",
  critical:
    "border-(--severity-critical)/35 text-(--severity-critical) bg-transparent",
  success: "border-(--risk-low-border) text-(--risk-low) bg-transparent",
  muted: "border-(--border) text-(--text-ter) bg-transparent",
  accent: "border-(--accent-border) text-(--accent) bg-transparent",
};

export function Badge({
  variant = "default",
  dot = false,
  className = "",
  children,
  ...props
}: BadgeProps) {
  return (
    <span
      className={[
        "pill-badge inline-flex items-center gap-1.5 border rounded-full font-semibold",
        styles[variant],
        className,
      ].join(" ")}
      {...props}
    >
      {dot && (
        <span
          className="h-1.5 w-1.5 rounded-full bg-current shrink-0"
          aria-hidden
        />
      )}
      {children}
    </span>
  );
}

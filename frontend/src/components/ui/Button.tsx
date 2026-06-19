import { type ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
}

const variantStyles: Record<Variant, string> = {
  primary:
    "bg-(--accent) text-(--text-inverse) border border-transparent hover:bg-(--accent-hover) hover:shadow-[var(--shadow-sm)] active:bg-(--accent-active)",
  secondary:
    "bg-(--surface) text-(--text-pri) border border-(--border) hover:bg-(--surface-el) hover:border-(--border-h)",
  ghost:
    "bg-transparent text-(--text-sec) border border-transparent hover:text-(--text-pri) hover:bg-(--surface-el)",
  danger:
    "bg-(--risk-high-soft) text-(--risk-high) border border-(--risk-high-border) hover:border-(--risk-high) hover:bg-(--risk-high-soft)",
};

const sizeStyles: Record<Size, string> = {
  sm: "h-8 px-3.5 text-(length:--text-xs) gap-1.5",
  md: "h-10 px-4.5 text-(length:--text-sm) gap-2",
  lg: "h-11 px-5.5 text-(length:--text-sm) gap-2.5",
};

export function Button({
  variant = "secondary",
  size = "md",
  loading = false,
  disabled,
  children,
  className = "",
  ...props
}: ButtonProps) {
  return (
    <button
      disabled={disabled || loading}
      className={[
        "inline-flex items-center justify-center rounded-[var(--radius-sm)] font-semibold",
        "transition-all duration-150 cursor-pointer select-none whitespace-nowrap",
        "disabled:opacity-45 disabled:cursor-not-allowed",
        "focus-visible:outline-2 focus-visible:outline-(--accent) focus-visible:outline-offset-2",
        variantStyles[variant],
        sizeStyles[size],
        className,
      ].join(" ")}
      {...props}
    >
      {loading && (
        <span
          className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent shrink-0"
          aria-hidden
        />
      )}
      {children}
    </button>
  );
}

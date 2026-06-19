import { type HTMLAttributes } from "react";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  elevated?: boolean;
  hover?: boolean;
}

export function Card({
  elevated = false,
  hover = false,
  className = "",
  children,
  ...props
}: CardProps) {
  return (
    <div
      className={[
        elevated ? "surface-card-lg" : "surface-card",
        hover
          ? "card-hover hover:border-(--border-h) cursor-pointer"
          : "",
        className,
      ].join(" ")}
      {...props}
    >
      {children}
    </div>
  );
}

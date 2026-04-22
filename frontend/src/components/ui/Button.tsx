import { type ButtonHTMLAttributes } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost";
  size?: "sm" | "md" | "lg";
  children: React.ReactNode;
}

export function Button({
  variant = "primary",
  size = "md",
  children,
  className = "",
  ...props
}: ButtonProps) {
  const base =
    variant === "primary"
      ? "btn-primary"
      : variant === "secondary"
        ? "btn-secondary"
        : "inline-flex items-center justify-center gap-2 text-[var(--color-text-secondary)] hover:text-[var(--color-text)] text-sm font-medium transition-colors cursor-pointer";

  const sizes = {
    sm: "text-xs px-3 py-1.5",
    md: "",
    lg: "text-base px-6 py-3",
  };

  return (
    <button className={`${base} ${sizes[size]} ${className}`} {...props}>
      {children}
    </button>
  );
}

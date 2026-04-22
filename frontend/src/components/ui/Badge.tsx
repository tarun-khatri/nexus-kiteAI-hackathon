interface BadgeProps {
  children: React.ReactNode;
  variant?: "orange" | "blue" | "green" | "red" | "gray" | "purple";
  className?: string;
}

export function Badge({ children, variant = "gray", className = "" }: BadgeProps) {
  return (
    <span className={`badge badge-${variant} ${className}`}>
      {children}
    </span>
  );
}

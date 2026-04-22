interface CardProps {
  children: React.ReactNode;
  className?: string;
  hover?: boolean;
  padding?: "sm" | "md" | "lg";
}

export function Card({ children, className = "", hover = false, padding = "md" }: CardProps) {
  const paddings = { sm: "p-4", md: "p-6", lg: "p-8" };
  return (
    <div className={`card ${hover ? "card-hover" : ""} ${paddings[padding]} ${className}`}>
      {children}
    </div>
  );
}

"use client";

interface NexusLogoProps {
  size?: "sm" | "md" | "lg";
  showText?: boolean;
  className?: string;
}

export function NexusLogo({ size = "md", showText = true, className = "" }: NexusLogoProps) {
  const sizes = { sm: 28, md: 36, lg: 48 };
  const textSizes = { sm: "text-lg", md: "text-xl", lg: "text-3xl" };
  const s = sizes[size];

  return (
    <div className={`flex items-center gap-2.5 ${className}`}>
      {/* Geometric "N" logo with connected nodes */}
      <svg width={s} height={s} viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id="nexus-grad" x1="0" y1="0" x2="48" y2="48" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#E86F2C" />
            <stop offset="100%" stopColor="#2563EB" />
          </linearGradient>
        </defs>
        {/* Background circle */}
        <rect width="48" height="48" rx="12" fill="url(#nexus-grad)" />
        {/* Letter N formed by nodes and connections */}
        <path
          d="M14 36V12L24 28L34 12V36"
          stroke="white"
          strokeWidth="3.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
        {/* Nodes at the vertices */}
        <circle cx="14" cy="36" r="3" fill="white" />
        <circle cx="14" cy="12" r="3" fill="white" />
        <circle cx="24" cy="28" r="3" fill="white" />
        <circle cx="34" cy="12" r="3" fill="white" />
        <circle cx="34" cy="36" r="3" fill="white" />
      </svg>
      {showText && (
        <span className={`font-heading font-bold tracking-tight ${textSizes[size]}`}>
          NEXUS
        </span>
      )}
    </div>
  );
}

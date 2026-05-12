"use client";

interface NexusLogoProps {
  size?: "sm" | "md" | "lg";
  showText?: boolean;
  className?: string;
}

/**
 * NEXUS logo.
 *
 * Design story (read by judges scanning the site):
 *   - Hexagonal frame  → Web3-native shape; signals "blockchain primitive"
 *   - Clean N letterform inside → brand name, the previous SVG accidentally
 *     drew an M (path went L→middle→R) so this is also a correctness fix
 *   - Four small nodes at the N's vertices → "agents in the economy"
 *   - One gold node (bottom-right) with an expanding ripple → "active
 *     payment in flight". The economy is RUNNING — even in the logo.
 *
 * The ripple is a tiny SVG <animate> — no GPU cost, no JS, no layout
 * thrash. Works in every modern browser. Disable it by setting the
 * `prefers-reduced-motion` media query at the CSS level if needed.
 */
export function NexusLogo({ size = "md", showText = true, className = "" }: NexusLogoProps) {
  const sizes = { sm: 28, md: 36, lg: 48 };
  const textSizes = { sm: "text-lg", md: "text-xl", lg: "text-3xl" };
  const s = sizes[size];

  return (
    <div className={`flex items-center gap-2.5 ${className}`}>
      <svg
        width={s}
        height={s}
        viewBox="0 0 48 48"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-label="NEXUS logo"
      >
        <defs>
          {/* Brand gradient — orange→blue, identical to existing brand tokens */}
          <linearGradient
            id="nexus-grad"
            x1="0"
            y1="0"
            x2="48"
            y2="48"
            gradientUnits="userSpaceOnUse"
          >
            <stop offset="0%" stopColor="#E86F2C" />
            <stop offset="100%" stopColor="#2563EB" />
          </linearGradient>
        </defs>

        {/* Hexagonal frame — Web3 native, replaces the boring rounded square */}
        <polygon
          points="24,2 44,12 44,36 24,46 4,36 4,12"
          fill="url(#nexus-grad)"
        />

        {/* CORRECT N letterform — bottom-left → top-left → bottom-right → top-right */}
        <path
          d="M15 34 L15 14 L33 34 L33 14"
          stroke="white"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />

        {/* Three static white nodes at three N vertices */}
        <circle cx="15" cy="34" r="2.4" fill="white" />
        <circle cx="15" cy="14" r="2.4" fill="white" />
        <circle cx="33" cy="14" r="2.4" fill="white" />

        {/* Fourth vertex = ACTIVE payment node (gold, with expanding ripple).
            This is the visual story: the economy is alive even in the icon. */}
        <circle cx="33" cy="34" r="3" fill="#FCD34D" />

        {/* Pulsing ripple emanating from the active node.
            Two layered animations make the ripple visibly travel outward. */}
        <circle
          cx="33"
          cy="34"
          r="3"
          fill="none"
          stroke="#FCD34D"
          strokeWidth="1.2"
          opacity="0.7"
        >
          <animate
            attributeName="r"
            values="3;9"
            dur="2s"
            repeatCount="indefinite"
          />
          <animate
            attributeName="opacity"
            values="0.7;0"
            dur="2s"
            repeatCount="indefinite"
          />
        </circle>
      </svg>
      {showText && (
        <span className={`font-heading font-bold tracking-tight ${textSizes[size]}`}>
          NEXUS
        </span>
      )}
    </div>
  );
}

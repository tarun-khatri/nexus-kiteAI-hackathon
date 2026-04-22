"use client";

/**
 * HashLink — renders a full identifier (tx hash, address, passport id,
 * mandate id, context hash, etc.) in a monospace one-line chip with
 * horizontal scroll when it overflows its container, and wraps it as an
 * anchor to the Kite block explorer when the `kind` has a URL mapping.
 *
 * Also shows a copy-to-clipboard button.
 *
 * No truncation. Ever. The full value is always in the DOM and always
 * copy/selectable.
 */

import { useState } from "react";
import { ExternalLink, Copy, Check } from "lucide-react";

export type HashKind =
  | "tx"         // transaction hash → /tx/0x...
  | "address"    // EVM address → /address/0x...
  | "passport"   // agent passport id → /address/0x...
  | "mandate"    // mandate id (not on-chain) → no link
  | "none";      // any other hash (traceability_hash, context_hash, report_hash)

const EXPLORER_BASE = "https://testnet.kitescan.ai";

function buildExplorerUrl(kind: HashKind, raw: string): string | null {
  if (!raw) return null;
  const trimmed = raw.trim();
  // Normalize the 0x prefix for hex kinds
  const hex = trimmed.startsWith("0x") || trimmed.startsWith("0X")
    ? trimmed
    : `0x${trimmed}`;

  switch (kind) {
    case "tx":
      return `${EXPLORER_BASE}/tx/${hex}`;
    case "address":
    case "passport":
      return `${EXPLORER_BASE}/address/${hex}`;
    case "mandate":
    case "none":
    default:
      return null;
  }
}

export function HashLink({
  value,
  kind = "none",
  label,
  className = "",
}: {
  value: string | null | undefined;
  kind?: HashKind;
  label?: string;
  className?: string;
}) {
  const [copied, setCopied] = useState(false);

  if (!value) {
    return (
      <span className="text-[11px] text-[var(--color-text-faint)] italic">
        (none)
      </span>
    );
  }

  const url = buildExplorerUrl(kind, value);

  const doCopy = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    try {
      navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      // ignore
    }
  };

  // Chip: monospace, single line, horizontal scroll when overflowing.
  const chipInner = (
    <span className="font-mono text-[11px] text-[var(--color-text-secondary)] whitespace-nowrap">
      {value}
    </span>
  );

  const chip = (
    <div className="flex-1 min-w-0 overflow-x-auto overflow-y-hidden no-scrollbar-thumb bg-[var(--color-bg-alt)] rounded px-2 py-1 border border-[var(--color-border)]">
      {url ? (
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 no-underline hover:text-[var(--color-blue)]"
          onClick={(e) => e.stopPropagation()}
        >
          {chipInner}
          <ExternalLink size={10} className="text-[var(--color-text-faint)] shrink-0" />
        </a>
      ) : (
        chipInner
      )}
    </div>
  );

  return (
    <div className={`inline-flex items-center gap-1.5 max-w-full ${className}`}>
      {label && (
        <span className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] shrink-0">
          {label}
        </span>
      )}
      {chip}
      <button
        type="button"
        onClick={doCopy}
        title={copied ? "Copied" : "Copy"}
        className="shrink-0 p-1 rounded hover:bg-[var(--color-bg-alt)] text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors"
      >
        {copied ? <Check size={12} className="text-[var(--color-green)]" /> : <Copy size={12} />}
      </button>
    </div>
  );
}

export default HashLink;

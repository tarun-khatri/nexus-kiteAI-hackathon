"use client";

import { NexusLogo } from "@/components/ui/NexusLogo";
import { ExternalLink } from "lucide-react";

export function Footer() {
  return (
    <footer className="py-16 border-t border-[var(--color-border)]">
      <div className="container-main">
        <div className="flex flex-col md:flex-row items-center justify-between gap-8">
          {/* Logo + tagline */}
          <div className="flex flex-col items-center md:items-start gap-2">
            <NexusLogo size="sm" />
            <p className="text-xs text-[var(--color-text-muted)]">
              The Living Agent Economy on Kite Chain
            </p>
          </div>

          {/* Links */}
          <div className="flex items-center gap-6 text-xs">
            <a
              href="https://testnet.kitescan.ai"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors no-underline"
            >
              <ExternalLink size={12} />
              Block Explorer
            </a>
            <a
              href="https://docs.gokite.ai"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors no-underline"
            >
              <ExternalLink size={12} />
              Kite Docs
            </a>
          </div>
        </div>

        {/* Bottom bar */}
        <div className="mt-10 pt-6 border-t border-[var(--color-border)] flex flex-col sm:flex-row items-center justify-between gap-4">
          <p className="text-[11px] text-[var(--color-text-muted)]">
            Built for the <strong>Kite AI Global Hackathon 2026</strong> — Track: Novel
          </p>
          <div className="flex items-center gap-4 text-[11px] text-[var(--color-text-muted)]">
            <span>Powered by Kite Chain (Testnet 2368)</span>
            <span>•</span>
            <span>Total infrastructure cost: <strong className="text-[var(--color-accent)]">$0</strong></span>
          </div>
        </div>
      </div>
    </footer>
  );
}

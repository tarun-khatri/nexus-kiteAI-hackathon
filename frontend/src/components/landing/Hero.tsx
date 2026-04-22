"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, ExternalLink } from "lucide-react";
import { getStats, type EconomyStats } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface AuditTotals {
  total: number;
}

export function Hero() {
  const [stats, setStats] = useState<EconomyStats | null>(null);
  const [auditTotal, setAuditTotal] = useState<number | null>(null);
  const [mandatesCompleted, setMandatesCompleted] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const [s, audit] = await Promise.all([
          getStats().catch(() => null),
          fetch(`${API_BASE}/api/audit-trail?limit=1`)
            .then((r) => (r.ok ? r.json() : null))
            .catch(() => null),
        ]);
        if (cancelled) return;
        if (s) setStats(s);
        if (audit && typeof audit.total === "number") setAuditTotal(audit.total);

        // Try mandates endpoint too (optional, graceful if missing)
        const mandates = await fetch(`${API_BASE}/api/mandates?limit=1`)
          .then((r) => (r.ok ? r.json() : null))
          .catch(() => null);
        if (!cancelled && mandates && typeof mandates.total === "number") {
          setMandatesCompleted(mandates.total);
        }
      } catch {
        // graceful — zeros will render
      }
    };

    load();
    const interval = setInterval(load, 15000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  const counters = [
    {
      value: stats?.economy.total_agents ?? 0,
      label: "Agents",
      format: (v: number) => String(v),
    },
    {
      value: stats ? Object.keys(stats.governance || {}).length : 0,
      label: "Capabilities",
      format: (v: number) => String(v),
    },
    {
      value: stats?.economy.total_transactions ?? 0,
      label: "On-Chain Payments",
      format: (v: number) => v.toLocaleString(),
    },
    {
      value: stats?.economy.total_volume_usdc ?? 0,
      label: "USDC Volume",
      format: (v: number) => `$${v.toFixed(4)}`,
    },
    {
      value: mandatesCompleted ?? stats?.economy.total_jobs_completed ?? 0,
      label: "Mandates",
      format: (v: number) => String(v),
    },
    {
      value: auditTotal ?? 0,
      label: "Audit Trails",
      format: (v: number) => String(v),
    },
  ];

  return (
    <section className="section-padding">
      <div className="container-main">
        <div className="grid grid-cols-1 lg:grid-cols-[1.15fr_1fr] gap-10 lg:gap-14 items-center">
          {/* LEFT — Copy + CTAs */}
          <div>
            {/* Chain pill */}
            <a
              href="https://testnet.kitescan.ai"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#FEF3E8] text-[var(--color-accent)] text-[11px] font-semibold tracking-wide mb-6 no-underline hover:bg-[#FDE6D1] transition-colors"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-accent)] animate-pulse" />
              Chain ID 2368 · Live on Kitescan
              <ExternalLink size={11} />
            </a>

            {/* Headline */}
            <h1 className="font-heading text-4xl sm:text-5xl lg:text-[56px] font-extrabold tracking-tight leading-[1.05] mb-5">
              AI agents that run
              <br />
              as{" "}
              <span className="text-[var(--color-accent)]">businesses.</span>
            </h1>

            {/* Subtitle */}
            <p className="text-[17px] sm:text-[18px] text-[var(--color-text-secondary)] leading-relaxed mb-8 max-w-xl">
              An open marketplace where{" "}
              <strong className="text-[var(--color-text)]">anyone</strong>{" "}
              registers an agent in one API call. Agents discover each other,
              pay via <strong className="text-[var(--color-text)]">x402</strong>, and
              build{" "}
              <strong className="text-[var(--color-text)]">on-chain reputation</strong> —
              live on Kite Aero testnet. Every transaction is verifiable.
            </p>

            {/* CTAs */}
            <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3 mb-6">
              <a
                href="#demo"
                className="btn-primary text-base px-6 py-3 no-underline inline-flex items-center gap-2"
              >
                Try live demo
                <ArrowRight size={16} />
              </a>
              <Link
                href="/dashboard"
                className="btn-secondary text-base px-6 py-3 no-underline"
              >
                Launch dashboard
              </Link>
            </div>

            <p className="text-xs text-[var(--color-text-muted)]">
              No signup · Real on-chain payments · ~15s end-to-end
            </p>
          </div>

          {/* RIGHT — Live counters panel */}
          <div className="relative">
            <div className="card p-6 sm:p-8 border-[var(--color-border)]">
              {/* Header strip */}
              <div className="flex items-center justify-between mb-5 pb-4 border-b border-[var(--color-border)]">
                <div className="flex items-center gap-2">
                  <span className="relative flex h-2.5 w-2.5">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--color-green)] opacity-75" />
                    <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-[var(--color-green)]" />
                  </span>
                  <span className="font-heading text-sm font-semibold">
                    Live on Kite Aero Testnet
                  </span>
                </div>
                <span className="text-[10px] text-[var(--color-text-muted)] font-mono">
                  auto-refresh 15s
                </span>
              </div>

              {/* Counters grid */}
              <div className="grid grid-cols-2 gap-x-6 gap-y-5">
                {counters.map((c) => (
                  <div key={c.label} className="animate-fade-in">
                    <div className="font-heading text-[28px] sm:text-[32px] font-extrabold text-[var(--color-text)] leading-none tracking-tight tabular-nums">
                      {c.format(c.value)}
                    </div>
                    <div className="text-[11px] text-[var(--color-text-muted)] mt-1.5 font-medium uppercase tracking-wider">
                      {c.label}
                    </div>
                  </div>
                ))}
              </div>

              {/* Footer strip */}
              <div className="mt-6 pt-4 border-t border-[var(--color-border)] flex items-center justify-end text-[11px] text-[var(--color-text-muted)]">
                <a
                  href="https://testnet.kitescan.ai"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-[var(--color-blue)] hover:underline no-underline"
                >
                  View on Kitescan
                  <ExternalLink size={10} />
                </a>
              </div>
            </div>

            {/* Subtle glow behind card */}
            <div
              className="absolute -inset-4 -z-10 opacity-60 blur-3xl"
              style={{
                background:
                  "radial-gradient(ellipse at 70% 30%, rgba(232,111,44,0.12), transparent 60%)",
              }}
            />
          </div>
        </div>
      </div>
    </section>
  );
}

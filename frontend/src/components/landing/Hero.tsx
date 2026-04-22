"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getStats, type EconomyStats } from "@/lib/api";

export function Hero() {
  const [stats, setStats] = useState<EconomyStats | null>(null);

  useEffect(() => {
    getStats().then(setStats).catch(() => {});
  }, []);

  const statItems = [
    { value: "4", label: "Smart Contracts", fallback: "4" },
    {
      value: stats ? `${stats.economy.total_transactions}+` : "100+",
      label: "On-Chain Payments",
      fallback: "100+",
    },
    {
      value: stats ? String(stats.economy.total_agents) : "8",
      label: "Active Agents",
      fallback: "8",
    },
    { value: "$0", label: "Infra Cost", fallback: "$0" },
  ];

  return (
    <section className="section-padding">
      <div className="container-main text-center">
        {/* Kite badge */}
        <div className="inline-flex items-center gap-2 badge badge-orange mb-6 text-xs">
          Built on Kite Chain
        </div>

        {/* Headline */}
        <h1 className="font-heading text-4xl sm:text-5xl lg:text-6xl font-extrabold tracking-tight leading-tight mb-6">
          The Living Agent Economy
          <br />
          <span className="text-[var(--color-accent)]">on Kite Chain</span>
        </h1>

        {/* Subtitle */}
        <p className="text-lg sm:text-xl text-[var(--color-text-secondary)] max-w-2xl mx-auto mb-10 leading-relaxed">
          Autonomous AI agents discover, hire, pay, and audit each other — all
          settled on-chain with x402 micropayments, zero human intervention.
        </p>

        {/* CTAs */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-16">
          <Link href="/dashboard" className="btn-primary text-base px-8 py-3 no-underline">
            Launch Dashboard
          </Link>
          <a href="#how-it-works" className="btn-secondary text-base px-8 py-3 no-underline">
            How It Works ↓
          </a>
        </div>

        {/* Live stats */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-6 max-w-3xl mx-auto">
          {statItems.map((item) => (
            <div key={item.label} className="text-center">
              <p className="font-heading text-3xl sm:text-4xl font-bold text-[var(--color-accent)]">
                {item.value}
              </p>
              <p className="text-xs sm:text-sm text-[var(--color-text-muted)] mt-1 font-medium">
                {item.label}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

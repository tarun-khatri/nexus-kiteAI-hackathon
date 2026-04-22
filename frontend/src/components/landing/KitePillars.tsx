"use client";

import { useEffect, useState } from "react";
import { Fingerprint, CreditCard, Scale } from "lucide-react";
import { HashLink } from "@/components/ui/HashLink";
import { getStats, getOnchainHistory } from "@/lib/api";

interface LiveMetrics {
  total_agents: number | null;
  total_payments: number | null;
  total_volume: number | null;
  total_mandates: number | null;
}

const AGENT_REGISTRY = "0xBf23C1A79EfEf28C170cC8895679C4b4E7A97a74";
const PAYMENT_ROUTER = "0xd76ea536704252DeD9602eCd549F776aD302c73C";
const REPUTATION_TRACKER = "0xeE38c91e1dd42A0fc6980Ba8ECc769DFfC5044a9";
const GOVERNANCE_RULES = "0xc7640Bf4fC973ac73bB381cb5a1f1f222db6671b";

function CodeBlock({ children }: { children: React.ReactNode }) {
  return (
    <pre className="text-[11px] font-mono bg-[var(--color-bg-alt)] border border-[var(--color-border)] rounded-lg p-3 overflow-x-auto leading-relaxed whitespace-pre text-[var(--color-text-secondary)]">
      {children}
    </pre>
  );
}

function Metric({ value, label }: { value: string; label: string }) {
  return (
    <div className="inline-flex items-baseline gap-1.5">
      <span className="font-heading text-[22px] font-extrabold text-[var(--color-accent)] tabular-nums leading-none">
        {value}
      </span>
      <span className="text-[11px] text-[var(--color-text-muted)] uppercase tracking-wider font-medium">
        {label}
      </span>
    </div>
  );
}

export function KitePillars() {
  const [metrics, setMetrics] = useState<LiveMetrics>({
    total_agents: null,
    total_payments: null,
    total_volume: null,
    total_mandates: null,
  });
  const [lastTxHash, setLastTxHash] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const [stats, history] = await Promise.all([
          getStats().catch(() => null),
          getOnchainHistory(1).catch(() => null),
        ]);
        if (cancelled) return;
        setMetrics({
          total_agents: stats?.economy.total_agents ?? 0,
          total_payments: stats?.economy.total_transactions ?? 0,
          total_volume: stats?.economy.total_volume_usdc ?? 0,
          total_mandates: stats?.economy.total_jobs_completed ?? 0,
        });
        if (history && history.payments && history.payments.length > 0) {
          // OnchainPayment doesn't include tx_hash directly — but we pass
          // the passport or mandate id as fallback. Most useful is the
          // mandate_id when present.
          const first = history.payments[0];
          setLastTxHash(first.mandate_id || null);
        }
      } catch {
        // graceful
      }
    };
    load();
    const int = setInterval(load, 20000);
    return () => {
      cancelled = true;
      clearInterval(int);
    };
  }, []);

  const fmt = (n: number | null, prefix = "", suffix = "") =>
    n == null ? "—" : `${prefix}${n.toLocaleString()}${suffix}`;
  const fmtUsd = (n: number | null) =>
    n == null ? "—" : `$${n.toFixed(4)}`;

  return (
    <section className="section-padding">
      <div className="container-main">
        {/* Header */}
        <div className="text-center mb-12">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#FEF3E8] text-[var(--color-accent)] text-[11px] font-semibold tracking-wide mb-4">
            The Kite Integration
          </div>
          <h2 className="font-heading text-2xl sm:text-3xl font-bold mb-3">
            Three Kite pillars. Wired end-to-end.
          </h2>
          <p className="text-[var(--color-text-secondary)] max-w-xl mx-auto">
            Not slideware. Every pillar below is backed by a deployed contract
            and a line of code running in production.
          </p>
        </div>

        {/* Pillars grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {/* === PILLAR 1: Agent Passport === */}
          <div className="card card-hover p-6 flex flex-col">
            <div className="w-11 h-11 rounded-xl flex items-center justify-center mb-5 bg-[#EFF6FF]">
              <Fingerprint size={22} className="text-[#2563EB]" />
            </div>
            <h3 className="font-heading text-lg font-bold mb-1">
              Agent Passport
            </h3>
            <p className="text-[11px] uppercase tracking-wider text-[var(--color-accent)] font-semibold mb-3">
              On-chain identity
            </p>
            <p className="text-sm text-[var(--color-text-secondary)] leading-relaxed mb-4">
              Every agent gets a deterministic passport, registered in
              AgentRegistry, queryable as a W3C-style DID.
            </p>

            <Metric
              value={fmt(metrics.total_agents)}
              label="Agents registered"
            />

            <div className="mt-4 mb-4">
              <CodeBlock>
{`passport_id = keccak256(
  "Nexus-DataAgent-v1"
)
# → 0xbd5585210c378b41…`}
              </CodeBlock>
            </div>

            <div className="mt-auto pt-4 border-t border-[var(--color-border)]">
              <p className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] font-semibold mb-1.5">
                AgentRegistry
              </p>
              <HashLink value={AGENT_REGISTRY} kind="address" />
            </div>
          </div>

          {/* === PILLAR 2: x402 Payments === */}
          <div className="card card-hover p-6 flex flex-col">
            <div className="w-11 h-11 rounded-xl flex items-center justify-center mb-5 bg-[#ECFDF5]">
              <CreditCard size={22} className="text-[#16A34A]" />
            </div>
            <h3 className="font-heading text-lg font-bold mb-1">
              x402 Micropayments
            </h3>
            <p className="text-[11px] uppercase tracking-wider text-[var(--color-accent)] font-semibold mb-3">
              Standards-compliant · on-chain settled
            </p>
            <p className="text-sm text-[var(--color-text-secondary)] leading-relaxed mb-4">
              Every service is x402-gated. Call without payment → HTTP 402 +
              <code className="font-mono text-[11px] mx-1">accepts</code>{" "}
              schema. Settles via the Pieverse facilitator.
            </p>

            <div className="flex items-center gap-4 flex-wrap">
              <Metric
                value={fmt(metrics.total_payments)}
                label="Payments settled"
              />
              <Metric value={fmtUsd(metrics.total_volume)} label="Volume" />
            </div>

            <div className="mt-4 mb-4">
              <CodeBlock>
{`POST /x402/data-agent
 → 402 + accepts[]  (gokite-aa)

POST /x402/data-agent
 + X-PAYMENT header
 → 200 + real data`}
              </CodeBlock>
            </div>

            <div className="mt-auto pt-4 border-t border-[var(--color-border)]">
              <p className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] font-semibold mb-1.5">
                PaymentRouter
              </p>
              <HashLink value={PAYMENT_ROUTER} kind="address" />
            </div>
          </div>

          {/* === PILLAR 3: Programmable Governance === */}
          <div className="card card-hover p-6 flex flex-col">
            <div className="w-11 h-11 rounded-xl flex items-center justify-center mb-5 bg-[#FFFBEB]">
              <Scale size={22} className="text-[#D97706]" />
            </div>
            <h3 className="font-heading text-lg font-bold mb-1">
              Programmable Governance
            </h3>
            <p className="text-[11px] uppercase tracking-wider text-[var(--color-accent)] font-semibold mb-3">
              Verified Intent
            </p>
            <p className="text-sm text-[var(--color-text-secondary)] leading-relaxed mb-4">
              Every query creates an ECDSA-signed mandate with budget,
              per-tx cap, and allowed-agents list. A 7-point circuit breaker
              gates every payment.
            </p>

            <Metric
              value={fmt(metrics.total_mandates)}
              label="Mandates completed"
            />

            <div className="mt-4 mb-4">
              <CodeBlock>
{`mandate = sign({
  query_hash, budget,
  max_per_tx,
  allowed_agents,
  ttl = 5m,
})
circuit_breaker(m, pay)
 → 7 checks → approve`}
              </CodeBlock>
            </div>

            <div className="mt-auto pt-4 border-t border-[var(--color-border)] space-y-2">
              <div>
                <p className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] font-semibold mb-1.5">
                  GovernanceRules
                </p>
                <HashLink value={GOVERNANCE_RULES} kind="address" />
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] font-semibold mb-1.5">
                  ReputationTracker
                </p>
                <HashLink value={REPUTATION_TRACKER} kind="address" />
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

"use client";

import { useEffect, useState } from "react";
import { ExternalLink } from "lucide-react";
import { HashLink } from "@/components/ui/HashLink";
import { getOnchainHistory, type OnchainPayment } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface AuditTrail {
  trail_id: string;
  traceability_hash?: string;
  report_hash?: string;
  on_chain_tx_hash?: string | null;
  query?: string;
  timestamp?: string;
}

const CONTRACTS = [
  {
    name: "AgentRegistry",
    address: "0xBf23C1A79EfEf28C170cC8895679C4b4E7A97a74",
    purpose: "Identity, capability registration",
  },
  {
    name: "PaymentRouter",
    address: "0xd76ea536704252DeD9602eCd549F776aD302c73C",
    purpose: "x402 micropayments, settlement",
  },
  {
    name: "ReputationTracker",
    address: "0xeE38c91e1dd42A0fc6980Ba8ECc769DFfC5044a9",
    purpose: "On-chain reputation scores",
  },
  {
    name: "GovernanceRules",
    address: "0xc7640Bf4fC973ac73bB381cb5a1f1f222db6671b",
    purpose: "Spending mandates + circuit breaker",
  },
];

function shortNameOrPassport(agent: string | null, passport: string): string {
  if (agent) {
    // Strip "Nexus-" prefix and "-v1" suffix for readability
    return agent.replace(/^Nexus-/, "").replace(/-v\d+$/, "");
  }
  return passport.slice(0, 10) + "…";
}

export function OnChainProof() {
  const [payments, setPayments] = useState<OnchainPayment[]>([]);
  const [trails, setTrails] = useState<AuditTrail[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const [history, audit] = await Promise.all([
          getOnchainHistory(5).catch(() => null),
          fetch(`${API_BASE}/api/audit-trail`)
            .then((r) => (r.ok ? r.json() : null))
            .catch(() => null),
        ]);
        if (history?.payments) setPayments(history.payments.slice(0, 5));
        if (audit?.trails) {
          const withTx: AuditTrail[] = audit.trails
            .filter((t: AuditTrail) => !!t.on_chain_tx_hash)
            .reverse()
            .slice(0, 5);
          setTrails(withTx);
        }
      } finally {
        setLoading(false);
      }
    };
    load();
    const int = setInterval(load, 20000);
    return () => clearInterval(int);
  }, []);

  return (
    <section id="contracts" className="section-padding bg-[var(--color-bg-alt)]">
      <div className="container-main">
        {/* Header */}
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white border border-[var(--color-border)] text-[11px] font-semibold text-[var(--color-text-secondary)] mb-4">
            <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-green)]" />
            Verifiable on Kite Aero Testnet
          </div>
          <h2 className="font-heading text-2xl sm:text-3xl font-bold mb-3">
            Everything above is on-chain right now.
          </h2>
          <p className="text-[var(--color-text-secondary)] max-w-xl mx-auto">
            These rows aren&apos;t mocks. Click any hash to open it in Kitescan.
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* === LEFT: Recent audit trails (real tx hashes) === */}
          <div className="card p-6">
            <div className="flex items-center justify-between mb-4 pb-3 border-b border-[var(--color-border)]">
              <h3 className="font-heading text-base font-bold">
                Recent audit-trail transactions
              </h3>
              <span className="text-[11px] text-[var(--color-text-muted)]">
                last {trails.length}
              </span>
            </div>

            {loading && trails.length === 0 ? (
              <div className="space-y-3">
                {[1, 2, 3].map((i) => (
                  <div
                    key={i}
                    className="h-8 bg-[var(--color-bg-alt)] rounded animate-pulse"
                  />
                ))}
              </div>
            ) : trails.length === 0 ? (
              <div className="py-8 text-center">
                <p className="text-sm text-[var(--color-text-muted)]">
                  No audit trails written yet.
                </p>
                <p className="text-xs text-[var(--color-text-faint)] mt-1">
                  Run a query above to produce the first one.
                </p>
              </div>
            ) : (
              <div className="space-y-2.5">
                {trails.map((t) => (
                  <div
                    key={t.trail_id}
                    className="flex items-start gap-3 py-2 border-b border-[var(--color-border)] last:border-0"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-xs text-[var(--color-text-secondary)] mb-1.5 line-clamp-1">
                        {t.query || t.trail_id}
                      </p>
                      <HashLink value={t.on_chain_tx_hash} kind="tx" />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* === RIGHT: Recent payments === */}
          <div className="card p-6">
            <div className="flex items-center justify-between mb-4 pb-3 border-b border-[var(--color-border)]">
              <h3 className="font-heading text-base font-bold">
                Recent on-chain payments
              </h3>
              <span className="text-[11px] text-[var(--color-text-muted)]">
                from PaymentRouter
              </span>
            </div>

            {loading && payments.length === 0 ? (
              <div className="space-y-3">
                {[1, 2, 3].map((i) => (
                  <div
                    key={i}
                    className="h-8 bg-[var(--color-bg-alt)] rounded animate-pulse"
                  />
                ))}
              </div>
            ) : payments.length === 0 ? (
              <div className="py-8 text-center">
                <p className="text-sm text-[var(--color-text-muted)]">
                  No payments settled yet.
                </p>
              </div>
            ) : (
              <div className="space-y-2.5">
                {payments.map((p) => (
                  <div
                    key={`${p.index}-${p.from_passport}`}
                    className="flex items-center gap-2 py-2 border-b border-[var(--color-border)] last:border-0 text-xs"
                  >
                    <span className="font-medium text-[var(--color-text)] truncate max-w-[100px]">
                      {shortNameOrPassport(p.from_agent, p.from_passport)}
                    </span>
                    <span className="text-[var(--color-text-muted)]">→</span>
                    <span className="font-medium text-[var(--color-text)] truncate max-w-[100px]">
                      {shortNameOrPassport(p.to_agent, p.to_passport)}
                    </span>
                    <span className="ml-auto font-mono tabular-nums text-[var(--color-accent)] font-semibold">
                      ${p.amount_usdc.toFixed(4)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Contracts strip */}
        <div className="mt-8 card p-6">
          <div className="flex items-center justify-between mb-4 pb-3 border-b border-[var(--color-border)]">
            <h3 className="font-heading text-base font-bold">
              Deployed contracts · Kite Aero Testnet
            </h3>
            <a
              href="https://testnet.kitescan.ai"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-xs text-[var(--color-blue)] hover:underline no-underline"
            >
              Explorer
              <ExternalLink size={11} />
            </a>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-3">
            {CONTRACTS.map((c) => (
              <div
                key={c.name}
                className="flex flex-col gap-1.5 py-2"
              >
                <div className="flex items-baseline justify-between gap-3">
                  <span className="font-heading font-semibold text-sm">
                    {c.name}
                  </span>
                  <span className="text-[11px] text-[var(--color-text-muted)] text-right">
                    {c.purpose}
                  </span>
                </div>
                <HashLink value={c.address} kind="address" />
              </div>
            ))}
          </div>
        </div>

        {/* Footer caption */}
        <p className="text-center text-xs text-[var(--color-text-muted)] mt-6">
          This page is static — the numbers above update live from the
          Kite Aero deployment. Chain ID 2368 · No server-side mocks.
        </p>
      </div>
    </section>
  );
}

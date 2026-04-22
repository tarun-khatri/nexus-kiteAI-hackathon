"use client";

import { Card } from "@/components/ui/Card";
import { Fingerprint, CreditCard, Scale } from "lucide-react";

const PILLARS = [
  {
    icon: Fingerprint,
    title: "Agent Passport",
    subtitle: "Identity on Kite Chain",
    description:
      "Every agent gets a deterministic passport ID registered in the AgentRegistry smart contract. Verifiable on-chain identity with W3C-inspired DID documents.",
    contract: "AgentRegistry",
    address: "0xBf23C1A79EfEf28C170cC8895679C4b4E7A97a74",
    color: "#2563EB",
    bgColor: "#EFF6FF",
  },
  {
    icon: CreditCard,
    title: "x402 Payments",
    subtitle: "Micropayments via Pieverse",
    description:
      "All agent services are x402-gated. Payments settle via the Pieverse facilitator on Kite testnet. HTTP 402 → X-PAYMENT header → on-chain settlement.",
    contract: "PaymentRouter",
    address: "0xd76ea536704252DeD9602eCd549F776aD302c73C",
    color: "#16A34A",
    bgColor: "#ECFDF5",
  },
  {
    icon: Scale,
    title: "Programmable Governance",
    subtitle: "Mandates + Circuit Breaker",
    description:
      "ECDSA-signed spending mandates with 7-point circuit breaker validation. Per-transaction limits, budget enforcement, reputation thresholds — all on-chain.",
    contract: "GovernanceRules",
    address: "0xc7640Bf4fC973ac73bB381cb5a1f1f222db6671b",
    color: "#D97706",
    bgColor: "#FFFBEB",
  },
];

export function KitePillars() {
  return (
    <section className="section-padding">
      <div className="container-main">
        {/* Header */}
        <div className="text-center mb-12">
          <h2 className="font-heading text-2xl sm:text-3xl font-bold mb-3">
            Built on Kite&apos;s Three Pillars
          </h2>
          <p className="text-[var(--color-text-secondary)] max-w-lg mx-auto">
            Identity, payments, and governance — the infrastructure for autonomous
            agent economies.
          </p>
        </div>

        {/* Pillars */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {PILLARS.map((pillar) => (
            <Card key={pillar.title} hover padding="lg">
              {/* Icon */}
              <div
                className="w-12 h-12 rounded-xl flex items-center justify-center mb-5"
                style={{ backgroundColor: pillar.bgColor }}
              >
                <pillar.icon size={24} style={{ color: pillar.color }} />
              </div>

              {/* Title */}
              <h3 className="font-heading text-lg font-semibold mb-1">
                {pillar.title}
              </h3>
              <p className="text-xs text-[var(--color-text-muted)] mb-3 font-medium">
                {pillar.subtitle}
              </p>

              {/* Description */}
              <p className="text-sm text-[var(--color-text-secondary)] leading-relaxed mb-5">
                {pillar.description}
              </p>

              {/* Contract address */}
              <div className="pt-4 border-t border-[var(--color-border)]">
                <p className="text-[10px] text-[var(--color-text-muted)] mb-1 font-medium uppercase tracking-wider">
                  {pillar.contract}
                </p>
                <a
                  href={`https://testnet.kitescan.ai/address/${pillar.address}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs font-mono text-[var(--color-blue)] hover:underline break-all"
                >
                  {pillar.address.slice(0, 20)}...{pillar.address.slice(-8)}
                </a>
              </div>
            </Card>
          ))}
        </div>
      </div>
    </section>
  );
}

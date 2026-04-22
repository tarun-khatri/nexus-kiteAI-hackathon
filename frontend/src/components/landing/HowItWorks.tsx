"use client";

import {
  Search,
  Brain,
  ShieldCheck,
  Zap,
  FileCheck2,
} from "lucide-react";

const STEPS = [
  {
    number: 1,
    icon: Search,
    title: "Submit Query",
    description:
      "Type any crypto question — token analysis, DeFi yields, rug-pull check, DEX liquidity. Natural language, any phrasing.",
  },
  {
    number: 2,
    icon: Brain,
    title: "LLM Discovers Agents",
    description:
      "An LLM reads the live agent catalog and decides which agents to hire based on their self-declared capabilities, reputation, and price.",
  },
  {
    number: 3,
    icon: ShieldCheck,
    title: "Mandate Signed",
    description:
      "A spending mandate is created with budget limits, allowed agents, and TTL — cryptographically signed with ECDSA. Circuit breaker validates every payment.",
  },
  {
    number: 4,
    icon: Zap,
    title: "Agents Execute & Pay",
    description:
      "Selected agents execute work and get paid via x402 micropayments. Every payment is a real on-chain transaction on Kite, verifiable on the block explorer.",
  },
  {
    number: 5,
    icon: FileCheck2,
    title: "Report + Audit Trail",
    description:
      "Results compiled into a report. Quality verified by AuditAgent. SHA-256 traceability hash recorded on-chain. Reputation scores updated.",
  },
];

export function HowItWorks() {
  return (
    <section id="how-it-works" className="section-padding">
      <div className="container-main">
        {/* Header */}
        <div className="text-center mb-16">
          <h2 className="font-heading text-2xl sm:text-3xl font-bold mb-3">
            How It Works
          </h2>
          <p className="text-[var(--color-text-secondary)] max-w-lg mx-auto">
            From query to on-chain settlement in under 30 seconds.
          </p>
        </div>

        {/* Desktop: horizontal stepper */}
        <div className="hidden lg:block">
          {/* Connecting line */}
          <div className="relative max-w-4xl mx-auto">
            <div className="absolute top-6 left-[10%] right-[10%] h-[2px] bg-[var(--color-border)]" />

            <div className="relative grid grid-cols-5 gap-4">
              {STEPS.map((step) => (
                <div key={step.number} className="flex flex-col items-center text-center">
                  {/* Number circle */}
                  <div className="relative z-10 w-12 h-12 rounded-full bg-[var(--color-accent)] text-white flex items-center justify-center font-heading font-bold text-lg shadow-md shadow-orange-200">
                    {step.number}
                  </div>
                  {/* Icon */}
                  <div className="mt-4 mb-2">
                    <step.icon size={22} className="text-[var(--color-text-muted)]" />
                  </div>
                  {/* Title */}
                  <h3 className="font-heading text-sm font-semibold mb-1.5">
                    {step.title}
                  </h3>
                  {/* Description */}
                  <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed px-1">
                    {step.description}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Tablet + Mobile: vertical stepper */}
        <div className="lg:hidden max-w-xl mx-auto">
          <div className="relative">
            {/* Vertical connecting line */}
            <div className="absolute left-6 top-0 bottom-0 w-[2px] bg-[var(--color-border)]" />

            <div className="space-y-8">
              {STEPS.map((step, i) => (
                <div key={step.number} className="relative flex gap-5">
                  {/* Number circle */}
                  <div className="relative z-10 shrink-0 w-12 h-12 rounded-full bg-[var(--color-accent)] text-white flex items-center justify-center font-heading font-bold text-lg shadow-md shadow-orange-200">
                    {step.number}
                  </div>
                  {/* Content */}
                  <div className="pt-1.5 pb-2">
                    <div className="flex items-center gap-2 mb-1">
                      <step.icon size={16} className="text-[var(--color-text-muted)]" />
                      <h3 className="font-heading text-base font-semibold">
                        {step.title}
                      </h3>
                    </div>
                    <p className="text-sm text-[var(--color-text-secondary)] leading-relaxed">
                      {step.description}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

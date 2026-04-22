"use client";

import { ExternalLink, CheckCircle2 } from "lucide-react";

const CONTRACTS = [
  {
    name: "AgentRegistry",
    purpose: "Agent identity, marketplace registration, capability discovery",
    address: "0xBf23C1A79EfEf28C170cC8895679C4b4E7A97a74",
  },
  {
    name: "PaymentRouter",
    purpose: "x402 micropayments, agent-to-agent settlement, balance tracking",
    address: "0xd76ea536704252DeD9602eCd549F776aD302c73C",
  },
  {
    name: "ReputationTracker",
    purpose: "On-chain reputation scores, quality-driven updates",
    address: "0xeE38c91e1dd42A0fc6980Ba8ECc769DFfC5044a9",
  },
  {
    name: "GovernanceRules",
    purpose: "Spending limits, daily caps, minimum reputation enforcement",
    address: "0xc7640Bf4fC973ac73bB381cb5a1f1f222db6671b",
  },
];

const EXPLORER_BASE = "https://testnet.kitescan.ai/address/";

export function ContractsTable() {
  return (
    <section id="contracts" className="section-padding bg-[var(--color-bg-alt)]">
      <div className="container-main">
        {/* Header */}
        <div className="text-center mb-12">
          <h2 className="font-heading text-2xl sm:text-3xl font-bold mb-3">
            Deployed on Kite Testnet
          </h2>
          <p className="text-[var(--color-text-secondary)] max-w-lg mx-auto">
            4 smart contracts, all live and verifiable. Every transaction is real.
          </p>
        </div>

        {/* Table */}
        <div className="card overflow-hidden max-w-4xl mx-auto">
          {/* Desktop table */}
          <div className="hidden sm:block">
            <table className="w-full">
              <thead>
                <tr className="border-b border-[var(--color-border)] bg-[var(--color-bg-alt)]">
                  <th className="text-left text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wider px-6 py-3">
                    Contract
                  </th>
                  <th className="text-left text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wider px-6 py-3">
                    Purpose
                  </th>
                  <th className="text-left text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wider px-6 py-3">
                    Address
                  </th>
                  <th className="text-right text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wider px-6 py-3">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody>
                {CONTRACTS.map((contract, i) => (
                  <tr
                    key={contract.name}
                    className={`border-b border-[var(--color-border)] last:border-0 hover:bg-[var(--color-bg-alt)]/50 transition-colors`}
                  >
                    <td className="px-6 py-4">
                      <span className="font-heading font-semibold text-sm">
                        {contract.name}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <span className="text-xs text-[var(--color-text-secondary)]">
                        {contract.purpose}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <a
                        href={`${EXPLORER_BASE}${contract.address}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1.5 text-xs font-mono text-[var(--color-blue)] hover:underline"
                      >
                        {contract.address.slice(0, 10)}...{contract.address.slice(-6)}
                        <ExternalLink size={12} />
                      </a>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <span className="inline-flex items-center gap-1 badge badge-green">
                        <CheckCircle2 size={12} />
                        Live
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Mobile cards */}
          <div className="sm:hidden divide-y divide-[var(--color-border)]">
            {CONTRACTS.map((contract) => (
              <div key={contract.name} className="p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-heading font-semibold text-sm">
                    {contract.name}
                  </span>
                  <span className="badge badge-green text-[10px]">Live</span>
                </div>
                <p className="text-xs text-[var(--color-text-secondary)]">
                  {contract.purpose}
                </p>
                <a
                  href={`${EXPLORER_BASE}${contract.address}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-[11px] font-mono text-[var(--color-blue)]"
                >
                  {contract.address.slice(0, 14)}...
                  <ExternalLink size={10} />
                </a>
              </div>
            ))}
          </div>
        </div>

        {/* Network info */}
        <div className="text-center mt-8 flex flex-wrap items-center justify-center gap-6 text-xs text-[var(--color-text-muted)]">
          <span>Network: <strong className="text-[var(--color-text)]">Kite Aero Testnet</strong></span>
          <span>Chain ID: <strong className="text-[var(--color-text)]">2368</strong></span>
          <span>
            Explorer:{" "}
            <a
              href="https://testnet.kitescan.ai"
              target="_blank"
              rel="noopener noreferrer"
              className="text-[var(--color-blue)] hover:underline"
            >
              testnet.kitescan.ai
            </a>
          </span>
        </div>
      </div>
    </section>
  );
}

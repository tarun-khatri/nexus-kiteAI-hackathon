"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getAgents, type AgentInfo } from "@/lib/api";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Users, ExternalLink } from "lucide-react";

const COLOR_PALETTE = [
  "#E86F2C", "#2563EB", "#16A34A", "#D97706", "#DC2626",
  "#7C3AED", "#0891B2", "#65A30D", "#EA580C", "#0D9488",
];

function hashString(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}

function colorFor(name: string): string {
  return COLOR_PALETTE[hashString(name) % COLOR_PALETTE.length];
}

function shortName(name: string): string {
  return name
    .replace(/^Nexus-/, "")
    .replace(/-v\d+$/, "")
    .replace(/Agent$/, "")
    .slice(0, 20) || name.slice(0, 20);
}

function sourceBadge(type?: string) {
  if (type === "http_callback") return <Badge variant="blue">Marketplace</Badge>;
  if (type === "on_chain_only") return <Badge variant="purple">On-Chain</Badge>;
  return <Badge variant="gray">Built-in</Badge>;
}

export function AgentShowcase() {
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getAgents()
      .then((data) => {
        // Hide on_chain_only entries — those are historical/inactive
        // passport rows pulled from AgentRegistry, not callable services.
        // The landing page should only show agents that can actually
        // serve queries right now.
        const active = (data.agents || []).filter(
          (a) => a.source_type !== "on_chain_only",
        );
        setAgents(active);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <section id="agents" className="section-padding bg-[var(--color-bg-alt)]">
      <div className="container-main">
        {/* Header */}
        <div className="text-center mb-12">
          <h2 className="font-heading text-2xl sm:text-3xl font-bold mb-3">
            Agent Marketplace
          </h2>
          <p className="text-[var(--color-text-secondary)] max-w-lg mx-auto">
            {agents.length > 0
              ? `${agents.length} agents registered and earning. Anyone can add more.`
              : "Start the backend to see live agents."}
          </p>
        </div>

        {/* Agent Grid */}
        {loading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {[1, 2, 3].map((i) => (
              <div key={i} className="card p-6 animate-pulse">
                <div className="h-4 bg-[var(--color-bg-alt)] rounded w-2/3 mb-4" />
                <div className="h-3 bg-[var(--color-bg-alt)] rounded w-full mb-2" />
                <div className="h-3 bg-[var(--color-bg-alt)] rounded w-3/4" />
              </div>
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {agents.map((agent) => {
              const color = colorFor(agent.name);
              const short = shortName(agent.name);

              return (
                <Card key={agent.agent_id} hover padding="md">
                  {/* Agent header */}
                  <div className="flex items-start justify-between mb-4">
                    <div className="flex items-center gap-3">
                      {/* Color avatar */}
                      <div
                        className="w-10 h-10 rounded-xl flex items-center justify-center text-white font-heading font-bold text-sm shrink-0"
                        style={{ backgroundColor: color }}
                      >
                        {short[0]?.toUpperCase()}
                      </div>
                      <div className="min-w-0">
                        <h3 className="font-heading text-sm font-semibold truncate">
                          {short}
                        </h3>
                        <p className="text-[11px] text-[var(--color-text-muted)] truncate">
                          {agent.name}
                        </p>
                      </div>
                    </div>
                    {sourceBadge(agent.source_type)}
                  </div>

                  {/* Description */}
                  <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed mb-4 line-clamp-2">
                    {agent.description || "No description provided."}
                  </p>

                  {/* Capabilities */}
                  <div className="flex flex-wrap gap-1.5 mb-4">
                    {(agent.capabilities || []).slice(0, 4).map((cap) => (
                      <span
                        key={cap}
                        className="text-[10px] px-2 py-0.5 rounded-full bg-[var(--color-bg-alt)] text-[var(--color-text-secondary)] font-medium"
                      >
                        {cap}
                      </span>
                    ))}
                    {(agent.capabilities || []).length > 4 && (
                      <span className="text-[10px] text-[var(--color-text-muted)]">
                        +{agent.capabilities.length - 4} more
                      </span>
                    )}
                  </div>

                  {/* Stats row */}
                  <div className="flex items-center justify-between pt-3 border-t border-[var(--color-border)]">
                    <div className="flex items-center gap-4 text-[11px] text-[var(--color-text-muted)]">
                      <span>
                        Rep:{" "}
                        <strong
                          className={
                            agent.reputation_score >= 70
                              ? "text-[var(--color-green)]"
                              : agent.reputation_score >= 40
                                ? "text-[var(--color-amber)]"
                                : "text-[var(--color-red)]"
                          }
                        >
                          {agent.reputation_score}
                        </strong>
                      </span>
                      <span>
                        Price:{" "}
                        <strong className="text-[var(--color-text)]">
                          ${agent.price_per_query}
                        </strong>
                      </span>
                    </div>
                    <span className="text-[11px] text-[var(--color-text-muted)]">
                      {agent.total_jobs_completed} jobs
                    </span>
                  </div>
                </Card>
              );
            })}
          </div>
        )}

        {/* CTA */}
        <div className="text-center mt-10">
          <Link
            href="/dashboard"
            className="btn-secondary inline-flex items-center gap-2 no-underline"
          >
            <Users size={16} />
            Register Your Agent →
          </Link>
        </div>
      </div>
    </section>
  );
}

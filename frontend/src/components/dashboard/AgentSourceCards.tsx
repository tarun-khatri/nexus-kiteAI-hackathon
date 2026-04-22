"use client";

import { CheckCircle2, XCircle, Database, Brain, Shield } from "lucide-react";
import type { LucideIcon } from "lucide-react";

interface AgentSource {
  name: string;
  capability: string;
  price: number;
  source: string;
  agent_id?: string;
}

interface AgentSourceCardsProps {
  agents: AgentSource[];
  auditScore?: number;
}

const ROLE_ICONS: Record<string, LucideIcon> = {
  data: Database,
  analyst: Brain,
  audit: Shield,
};

function getIcon(name: string): LucideIcon {
  const lower = name.toLowerCase();
  if (lower.includes("data") || lower.includes("defi") || lower.includes("dex")) return Database;
  if (lower.includes("analyst") || lower.includes("security")) return Brain;
  if (lower.includes("audit")) return Shield;
  return Database;
}

// (shortName removed — we now show the full agent name.)

export function AgentSourceCards({ agents, auditScore }: AgentSourceCardsProps) {
  if (!agents || agents.length === 0) return null;

  return (
    <div>
      <p className="text-[11px] font-medium text-[var(--color-text-muted)] uppercase tracking-wider mb-3">
        Agent Sources
      </p>
      <div className="flex flex-wrap gap-3">
        {agents.map((agent, i) => {
          const Icon = getIcon(agent.name);
          const isAudit = agent.capability?.includes("audit") || agent.name.toLowerCase().includes("audit");
          const isMarketplace = agent.source === "marketplace";

          return (
            <div
              key={i}
              className="card p-3 flex-1 min-w-[200px] max-w-[280px] hover:shadow-md transition-shadow"
            >
              <div className="flex items-start gap-2 mb-2">
                <div className="w-7 h-7 rounded-lg bg-[var(--color-bg-alt)] flex items-center justify-center shrink-0">
                  <Icon size={14} className="text-[var(--color-accent)]" />
                </div>
                <div className="min-w-0 flex-1">
                  {/* Full agent name, no truncation. Wraps across lines for long names. */}
                  <p className="text-xs font-semibold break-words leading-tight">{agent.name}</p>
                  {isMarketplace && (
                    <span className="badge badge-blue text-[8px] mt-1 inline-block">EXT</span>
                  )}
                </div>
              </div>

              <p className="text-[11px] text-[var(--color-text-muted)] mb-2">
                {agent.capability?.replace(/_/g, " ")}
              </p>

              <div className="flex items-center justify-between">
                <span className="text-[11px] font-mono text-[var(--color-text-secondary)]">
                  ${agent.price?.toFixed(4)}
                </span>
                {isAudit && auditScore !== undefined ? (
                  <span className={`text-[11px] font-semibold ${auditScore >= 70 ? "text-[var(--color-green)]" : "text-[var(--color-red)]"}`}>
                    {auditScore}/100
                  </span>
                ) : (
                  <CheckCircle2 size={14} className="text-[var(--color-green)]" />
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

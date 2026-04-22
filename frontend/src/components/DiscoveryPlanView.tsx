"use client";

import type { DiscoveryPlan } from "@/lib/api";
import { Route, AlertCircle } from "lucide-react";

export function DiscoveryPlanView({ plan }: { plan: DiscoveryPlan }) {
  if (!plan) return null;

  return (
    <div className="card border-l-4 border-l-[var(--color-purple)] p-5 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Route size={16} className="text-[var(--color-purple)]" />
          <h4 className="font-heading text-sm font-semibold">Discovery Plan</h4>
        </div>
        <div className="flex items-center gap-2">
          <span className="badge badge-gray">{plan.query_type}</span>
          <span className="text-[11px] text-[var(--color-text-muted)]">
            conf: {(plan.confidence * 100).toFixed(0)}%
          </span>
        </div>
      </div>

      {/* Selected agents */}
      {plan.agents_selected && plan.agents_selected.length > 0 && (
        <div className="space-y-1.5">
          {plan.agents_selected.map((agent, i) => (
            <div key={i} className="flex items-center justify-between py-2 px-3 rounded-lg bg-[var(--color-bg-alt)]">
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-[11px] font-heading font-bold text-[var(--color-text-muted)] w-5">{i + 1}.</span>
                <span className="text-xs font-medium truncate">{agent.agent}</span>
                <span className={`badge text-[9px] ${agent.source === "marketplace" ? "badge-blue" : "badge-gray"}`}>
                  {agent.source}
                </span>
              </div>
              <div className="flex items-center gap-3 text-[11px] text-[var(--color-text-muted)] shrink-0">
                <span className="font-mono">${agent.price}</span>
                <span>rep:{agent.reputation}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Missing capabilities */}
      {plan.missing_capabilities && plan.missing_capabilities.length > 0 && (
        <div className="flex items-start gap-2 p-3 rounded-lg bg-amber-50 border border-amber-200">
          <AlertCircle size={14} className="text-[var(--color-amber)] shrink-0 mt-0.5" />
          <div>
            <p className="text-xs font-medium text-[var(--color-amber)]">Missing capabilities</p>
            <div className="flex flex-wrap gap-1 mt-1">
              {plan.missing_capabilities.map((cap) => (
                <span key={cap} className="badge badge-orange text-[9px]">{cap}</span>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Summary */}
      <div className="flex items-center justify-between text-[11px] text-[var(--color-text-muted)] pt-1">
        <span>
          Est. cost: <strong className="text-[var(--color-text)]">${plan.estimated_cost?.toFixed(4)}</strong>
        </span>
        {plan.complete !== undefined && (
          <span className={plan.complete ? "text-[var(--color-green)]" : "text-[var(--color-amber)]"}>
            {plan.complete ? "All capabilities covered" : "Partial coverage"}
          </span>
        )}
      </div>
    </div>
  );
}

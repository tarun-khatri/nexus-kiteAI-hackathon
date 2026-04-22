"use client";

import { ShieldAlert } from "lucide-react";

interface CircuitBreakerEvent {
  approved?: boolean;
  verdict?: string;
  mandate_id?: string;
  amount?: number;
  to_agent?: string;
  detail?: string;
  budget_remaining?: number;
  reason?: string;
}

export default function CircuitBreakerAlert({ block }: { block: CircuitBreakerEvent }) {
  return (
    <div className="card border-l-4 border-l-[var(--color-red)] p-4 animate-fade-in">
      <div className="flex items-start gap-3">
        <div className="shrink-0 w-9 h-9 rounded-lg bg-red-50 flex items-center justify-center">
          <ShieldAlert size={18} className="text-[var(--color-red)]" />
        </div>
        <div className="flex-1 min-w-0">
          <h4 className="font-heading text-sm font-semibold text-[var(--color-red)]">
            Circuit Breaker Blocked
          </h4>
          <p className="text-xs text-[var(--color-text-secondary)] mt-1 leading-relaxed">
            {block.reason || block.detail || "Payment blocked by circuit breaker"}
          </p>
          <div className="flex flex-wrap gap-4 mt-2 text-[11px] text-[var(--color-text-muted)]">
            {block.to_agent && (
              <span>Agent: <strong className="text-[var(--color-text)]">{block.to_agent}</strong></span>
            )}
            {block.amount !== undefined && (
              <span>Amount: <strong className="text-[var(--color-text)]">${block.amount.toFixed(4)}</strong></span>
            )}
            {block.budget_remaining !== undefined && (
              <span>Budget left: <strong className="text-[var(--color-text)]">${block.budget_remaining.toFixed(4)}</strong></span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

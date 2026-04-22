"use client";

/**
 * TransactionFeed — live activity stream.
 *
 * Rules:
 *   • Full agent names, no slice().
 *   • Full UTC datetime on every row: "2026-04-21 10:19:27 UTC".
 *   • Every tx_hash (payment_sent, audit_trail_recorded, reputation_update,
 *     work_completed when tied to chain, etc.) rendered as a clickable
 *     `<HashLink kind="tx">`.
 *   • Mandate IDs rendered full; agent-discovery messages use the new
 *     structured fields (capabilities, agent_names, missing_capabilities).
 *   • No 50-event cap here — the provider already caps at 500.
 */

import type { NexusEvent } from "@/hooks/WebSocketProvider";
import { HashLink } from "@/components/ui/HashLink";
import {
  ArrowRightLeft, Search, Play, CheckCircle2, Shield, ShieldAlert,
  Star, FileText, FileBadge, Settings, Bell, Info, FileCheck, Stamp,
  Fingerprint,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

const EVENT_CONFIG: Record<string, { icon: LucideIcon; color: string; border: string }> = {
  payment_sent:             { icon: ArrowRightLeft, color: "text-[var(--color-green)]",  border: "border-l-[var(--color-green)]" },
  payment_received:         { icon: ArrowRightLeft, color: "text-[var(--color-green)]",  border: "border-l-[var(--color-green)]" },
  payment_confirmed:        { icon: CheckCircle2,   color: "text-[var(--color-green)]",  border: "border-l-[var(--color-green)]" },
  work_started:             { icon: Play,           color: "text-[var(--color-blue)]",   border: "border-l-[var(--color-blue)]" },
  work_completed:           { icon: CheckCircle2,   color: "text-[var(--color-blue)]",   border: "border-l-[var(--color-blue)]" },
  agent_discovery:          { icon: Search,         color: "text-[var(--color-purple)]", border: "border-l-[var(--color-purple)]" },
  audit_completed:          { icon: FileCheck,      color: "text-[var(--color-amber)]",  border: "border-l-[var(--color-amber)]" },
  reputation_update:        { icon: Star,           color: "text-[var(--color-purple)]", border: "border-l-[var(--color-purple)]" },
  report_started:           { icon: FileText,       color: "text-[var(--color-text-muted)]", border: "border-l-[var(--color-border)]" },
  report_completed:         { icon: FileBadge,      color: "text-[var(--color-green)]",  border: "border-l-[var(--color-green)]" },
  mandate_created:          { icon: Stamp,          color: "text-[var(--color-accent)]", border: "border-l-[var(--color-accent)]" },
  mandate_completed:        { icon: Stamp,          color: "text-[var(--color-accent)]", border: "border-l-[var(--color-accent)]" },
  circuit_breaker_approved: { icon: Shield,         color: "text-[var(--color-green)]",  border: "border-l-[var(--color-green)]" },
  circuit_breaker_blocked:  { icon: ShieldAlert,    color: "text-[var(--color-red)]",    border: "border-l-[var(--color-red)]" },
  audit_trail_recorded:     { icon: FileCheck,      color: "text-[var(--color-green)]",  border: "border-l-[var(--color-green)]" },
  governance_rule_changed:  { icon: Settings,       color: "text-[var(--color-amber)]",  border: "border-l-[var(--color-amber)]" },
  alert_triggered:          { icon: Bell,           color: "text-[var(--color-red)]",    border: "border-l-[var(--color-red)]" },
  agent_identity_resolved:  { icon: Fingerprint,    color: "text-[var(--color-blue)]",   border: "border-l-[var(--color-blue)]" },
  system_info:              { icon: Info,           color: "text-[var(--color-text-muted)]", border: "border-l-[var(--color-border)]" },
};

const DEFAULT_CFG = { icon: Info, color: "text-[var(--color-text-muted)]", border: "border-l-[var(--color-border)]" };

function formatUtc(ts: string): string {
  try {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return ts || "";
    return d.toISOString().replace("T", " ").slice(0, 19) + " UTC";
  } catch {
    return ts || "";
  }
}

/**
 * Per-event rendering. Returns a React fragment. Full agent names, full
 * identifiers, full queries — nothing truncated.
 */
function renderEventBody(e: NexusEvent): React.ReactNode {
  const d = e.data || {};
  const agent = e.agent || "";
  const target = e.target || "";

  switch (e.event) {
    case "payment_sent":
      return (
        <div>
          <p className="text-[12px] leading-snug">
            <span className="font-medium">{agent}</span>
            <span className="text-[var(--color-text-muted)]"> → </span>
            <span className="font-medium">{target}</span>
            <span className="text-[var(--color-text-muted)]">
              {" "}${typeof d.amount === "number" ? d.amount.toFixed(4) : "?"} ({d.purpose || "payment"})
            </span>
          </p>
          {d.tx_hash && <HashLink value={d.tx_hash} kind="tx" label="tx" className="mt-1" />}
        </div>
      );

    case "agent_discovery": {
      // Prefer new structured fields; fall back to backend's `message`.
      const caps = Array.isArray(d.capabilities) ? d.capabilities : [];
      const missing = Array.isArray(d.missing_capabilities) ? d.missing_capabilities : [];
      const names = Array.isArray(d.agent_names) ? d.agent_names : [];
      if (caps.length) {
        return (
          <p className="text-[12px] leading-snug">
            <span className="font-medium">{agent}</span> routed to{" "}
            <strong>{caps.length}</strong> agent(s):{" "}
            <code className="font-mono text-[11px]">{caps.join(", ")}</code>
            {names.length > 0 && (
              <span className="text-[var(--color-text-muted)]"> ({names.join(", ")})</span>
            )}
          </p>
        );
      }
      if (missing.length) {
        return (
          <p className="text-[12px] leading-snug">
            <span className="font-medium">{agent}</span>: no agent found for{" "}
            <code className="font-mono text-[11px]">{missing.join(", ")}</code>
          </p>
        );
      }
      return <p className="text-[12px] leading-snug">{e.message || "Discovery"}</p>;
    }

    case "work_started":
      return (
        <p className="text-[12px] leading-snug">
          <span className="font-medium">{agent}</span> started{d.task ? `: ${d.task}` : " work"}
        </p>
      );

    case "work_completed": {
      const dur = typeof d.duration_ms === "number" ? (d.duration_ms / 1000).toFixed(2) : "?";
      return (
        <div>
          <p className="text-[12px] leading-snug">
            <span className="font-medium">{agent}</span> done ({dur}s)
          </p>
          {d.tx_hash && <HashLink value={d.tx_hash} kind="tx" label="tx" className="mt-1" />}
        </div>
      );
    }

    case "reputation_update":
      return (
        <div>
          <p className="text-[12px] leading-snug">
            <span className="font-medium">{agent}</span> reputation: {d.old_score ?? "?"} → {d.new_score ?? "?"}
          </p>
          {d.tx_hash && <HashLink value={d.tx_hash} kind="tx" label="tx" className="mt-1" />}
        </div>
      );

    case "circuit_breaker_approved":
      return (
        <p className="text-[12px] leading-snug">
          Circuit breaker: <strong className="text-[var(--color-green)]">APPROVED</strong>{" "}
          ${typeof d.amount === "number" ? d.amount.toFixed(4) : "?"} →{" "}
          <span className="font-medium">{target || d.to_agent || "?"}</span>
        </p>
      );

    case "circuit_breaker_blocked":
      return (
        <p className="text-[12px] leading-snug">
          Circuit breaker: <strong className="text-[var(--color-red)]">BLOCKED</strong>{" "}
          ${typeof d.amount === "number" ? d.amount.toFixed(4) : "?"} →{" "}
          <span className="font-medium">{target || d.to_agent || "?"}</span>
          {d.detail && <span className="text-[var(--color-text-muted)]"> ({d.detail})</span>}
        </p>
      );

    case "mandate_created":
      return (
        <div className="space-y-1">
          <p className="text-[12px] leading-snug">
            Mandate created — budget ${typeof d.total_budget === "number" ? d.total_budget.toFixed(4) : "?"}
          </p>
          <HashLink value={d.mandate_id} kind="mandate" label="id" />
          {d.signer && <HashLink value={d.signer} kind="address" label="signer" />}
        </div>
      );

    case "mandate_completed":
      return (
        <div className="space-y-1">
          <p className="text-[12px] leading-snug">
            Mandate completed — spent ${typeof d.total_spent === "number" ? d.total_spent.toFixed(4) : "?"} /
            ${typeof d.total_budget === "number" ? d.total_budget.toFixed(4) : "?"}
          </p>
          <HashLink value={d.mandate_id} kind="mandate" label="id" />
        </div>
      );

    case "audit_completed":
      return (
        <p className="text-[12px] leading-snug">
          Audit: {d.quality_score ?? 0}/100 ({d.checks?.length ?? 0} checks)
        </p>
      );

    case "audit_trail_recorded":
      return (
        <div>
          <p className="text-[12px] leading-snug">
            Audit trail{" "}
            {d.chain_status === "pending"
              ? <span className="text-[var(--color-amber)]">recording on-chain…</span>
              : <span className="text-[var(--color-green)]">recorded on-chain</span>}
          </p>
          {d.trail_id && <HashLink value={d.trail_id} kind="none" label="trail" />}
          {d.on_chain_tx_hash && <HashLink value={d.on_chain_tx_hash} kind="tx" label="tx" className="mt-1" />}
        </div>
      );

    case "report_started":
      return (
        <p className="text-[12px] leading-snug break-words">
          Report started: <span className="italic text-[var(--color-text-secondary)]">"{d.query || "?"}"</span>
        </p>
      );

    case "report_completed":
      return (
        <p className="text-[12px] leading-snug">
          Report done — ${typeof d.total_cost === "number" ? d.total_cost.toFixed(4) : "?"} /{" "}
          {d.agents_involved ?? "?"} agent(s) / {typeof d.time_ms === "number" ? (d.time_ms / 1000).toFixed(1) : "?"}s
        </p>
      );

    case "system_info":
      return <p className="text-[12px] leading-snug">{e.message || "System info"}</p>;

    default:
      // Unknown event type: render the backend's message as-is, full length.
      return <p className="text-[12px] leading-snug break-words">{e.message || e.event}</p>;
  }
}

export function TransactionFeed({ events }: { events: NexusEvent[] }) {
  if (!events || events.length === 0) {
    return (
      <div className="flex items-center justify-center py-12 text-[var(--color-text-muted)] text-sm">
        Submit a query to see live agent activity here.
      </div>
    );
  }

  return (
    <div className="space-y-0.5">
      {events.map((event, i) => {
        const cfg = EVENT_CONFIG[event.event] || DEFAULT_CFG;
        const Icon = cfg.icon;
        const ts = formatUtc(event.timestamp);
        const isNew = i === 0;

        return (
          <div
            key={`${event.timestamp}-${i}`}
            className={`flex items-start gap-2 py-2 px-2.5 border-l-[3px] ${cfg.border} rounded-r transition-all ${
              isNew ? "bg-[var(--color-bg-alt)]" : "hover:bg-[var(--color-input)]"
            }`}
          >
            <div className={`shrink-0 mt-0.5 ${cfg.color}`}>
              <Icon size={13} />
            </div>
            <div className="flex-1 min-w-0 space-y-0.5">
              {renderEventBody(event)}
              <span className="block text-[10px] font-mono text-[var(--color-text-faint)] pt-0.5">
                {ts}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

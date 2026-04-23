"use client";

/**
 * /pulse — Market Pulse public page (v2).
 *
 * Shows autonomous runs: every 15 minutes the backend wakes itself up,
 * generates a query from live market signals via LLM, and drives it through
 * the full orchestrator (mandate → x402 payment → audit trail) with no human
 * involvement. Every row here has a clickable Kitescan tx — live on-chain
 * proof.
 *
 * v2 additions:
 *   - Rows are click-to-expand. Expanded panel shows full mandate detail
 *     (ECDSA signature, signer, budget, payment log), every individual x402
 *     payment as a clickable tx, and the audit trail hash.
 *   - Each row shows a query-source badge: 🧠 llm-generated, 📋 from registry
 *     example queries, 📌 built-in fallback.
 *
 * Judges bookmark this URL. New runs arrive via WebSocket event
 * `pulse_run_completed` and the row list re-fetches on a 15s timer as a
 * fallback.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Activity,
  Play,
  AlertCircle,
  Loader2,
  RefreshCw,
  Clock,
  ExternalLink,
  ChevronDown,
  ChevronRight,
  Brain,
  BookOpen,
  Pin,
  CheckCircle2,
  XCircle,
  ShieldCheck,
} from "lucide-react";

import {
  getPulseRuns,
  getPulseStatus,
  getPulseRun,
  triggerPulse,
  type PulseRun,
  type PulseRunDetail,
  type PulseStatus,
  type PulseQuerySource,
} from "@/lib/api";
import { HashLink } from "@/components/ui/HashLink";
import { NexusLogo } from "@/components/ui/NexusLogo";
import {
  WebSocketProvider,
  useWebSocketContext,
} from "@/hooks/WebSocketProvider";

// ======================================================================
// Helpers
// ======================================================================

function timeAgo(iso: string | null): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (!isFinite(then)) return "—";
  const sec = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ${min % 60}m ago`;
  const d = Math.floor(hr / 24);
  return `${d}d ago`;
}

function countdown(targetIso: string | null): string {
  if (!targetIso) return "—";
  const target = new Date(targetIso).getTime();
  if (!isFinite(target)) return "—";
  const diff = Math.max(0, Math.floor((target - Date.now()) / 1000));
  if (diff === 0) return "now";
  const min = Math.floor(diff / 60);
  const sec = diff % 60;
  return `${min}:${sec.toString().padStart(2, "0")}`;
}

function avgCost(runs: PulseRun[]): string {
  const ok = runs.filter((r) => r.status === "ok");
  if (ok.length === 0) return "—";
  const total = ok.reduce((a, r) => a + (r.total_cost_usdc || 0), 0);
  return `$${(total / ok.length).toFixed(4)}`;
}

function formatUtc(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toISOString().replace("T", " ").replace(/\..+Z$/, " UTC");
  } catch {
    return iso;
  }
}

function querySourceMeta(source: PulseQuerySource | undefined | null) {
  switch (source) {
    case "llm_generated":
      return {
        icon: Brain,
        label: "LLM-generated",
        color: "#7C3AED",
        bg: "#F5F3FF",
      };
    case "capability_registry":
      return {
        icon: BookOpen,
        label: "From agent registry",
        color: "#2563EB",
        bg: "#EFF6FF",
      };
    case "built_in_fallback":
      return {
        icon: Pin,
        label: "Built-in fallback",
        color: "#6B7280",
        bg: "#F3F4F6",
      };
    case "manual":
      return {
        icon: Play,
        label: "Manual trigger",
        color: "#D97706",
        bg: "#FFFBEB",
      };
    default:
      return {
        icon: Activity,
        label: "—",
        color: "#9CA3AF",
        bg: "#F3F4F6",
      };
  }
}

// ======================================================================
// Inner component (wrapped by WebSocketProvider)
// ======================================================================

function PulseInner() {
  const [runs, setRuns] = useState<PulseRun[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [status, setStatus] = useState<PulseStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [triggering, setTriggering] = useState<boolean>(false);
  const [triggerError, setTriggerError] = useState<string | null>(null);
  const [tickTs, setTickTs] = useState<number>(() => Date.now());

  // Drill-down state: one row expanded at a time, details cached after
  // first fetch so collapse/re-expand is instant.
  const [expandedRunId, setExpandedRunId] = useState<string | null>(null);
  const [details, setDetails] = useState<Map<string, PulseRunDetail>>(
    new Map(),
  );
  const [detailsLoading, setDetailsLoading] = useState<string | null>(null);
  const [detailsError, setDetailsError] = useState<{ id: string; msg: string } | null>(null);

  const { events } = useWebSocketContext();

  const refresh = useCallback(async () => {
    try {
      const [runsRes, statusRes] = await Promise.all([
        getPulseRuns(50).catch(() => null),
        getPulseStatus().catch(() => null),
      ]);
      if (runsRes) {
        setRuns(runsRes.runs || []);
        setTotal(runsRes.total || 0);
      }
      if (statusRes) setStatus(statusRes);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const int = setInterval(refresh, 15000);
    return () => clearInterval(int);
  }, [refresh]);

  // Countdown re-render every second (no data fetch)
  useEffect(() => {
    const int = setInterval(() => setTickTs(Date.now()), 1000);
    return () => clearInterval(int);
  }, []);

  // Refresh list when a pulse event arrives
  useEffect(() => {
    if (events.length === 0) return;
    const latest = events[0];
    if (
      latest.event === "pulse_run_completed" ||
      latest.event === "pulse_run_failed"
    ) {
      setTimeout(refresh, 500);
    }
  }, [events, refresh]);

  const toggleExpand = async (runId: string) => {
    if (expandedRunId === runId) {
      setExpandedRunId(null);
      return;
    }
    setExpandedRunId(runId);
    setDetailsError(null);

    if (details.has(runId)) return; // already cached

    setDetailsLoading(runId);
    try {
      const d = await getPulseRun(runId);
      // Backend returns 404 as JSON {error: "not_found", ...} — detect
      const withError = d as unknown as { error?: string; message?: string };
      if (withError.error) {
        setDetailsError({
          id: runId,
          msg: withError.message || withError.error,
        });
      } else {
        setDetails((prev) => new Map(prev).set(runId, d));
      }
    } catch (e: any) {
      setDetailsError({ id: runId, msg: e?.message || "Failed to load details" });
    } finally {
      setDetailsLoading(null);
    }
  };

  const handleTrigger = async () => {
    if (triggering) return;
    setTriggering(true);
    setTriggerError(null);
    try {
      const res = await triggerPulse();
      if ("error" in res) {
        setTriggerError(
          res.message || "Trigger rate-limited. Try again in a moment.",
        );
      } else {
        await refresh();
      }
    } catch (e: any) {
      setTriggerError(e?.message || "Trigger failed");
    } finally {
      setTriggering(false);
    }
  };

  const statusStrip = useMemo(() => {
    if (!status) return null;
    void tickTs; // trigger re-render each second for countdown
    return (
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <StatBox label="Total runs" value={total.toLocaleString()} />
        <StatBox
          label="Last run"
          value={status.last_run_at ? timeAgo(status.last_run_at) : "—"}
        />
        <StatBox
          label="Next run"
          value={status.enabled ? countdown(status.next_run_at) : "disabled"}
        />
        <StatBox label="Avg cost / run" value={avgCost(runs)} />
      </div>
    );
  }, [status, total, runs, tickTs]);

  return (
    <div className="min-h-screen bg-[var(--color-bg)]">
      <header className="sticky top-0 z-50 bg-white/95 backdrop-blur-md border-b border-[var(--color-border)]">
        <div className="container-main flex items-center justify-between h-14">
          <div className="flex items-center gap-3">
            <Link
              href="/"
              className="text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors no-underline"
            >
              <ArrowLeft size={16} />
            </Link>
            <NexusLogo size="sm" showText={false} />
            <span className="font-heading font-bold text-sm">NEXUS</span>
            <span className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wider font-semibold px-2 py-0.5 rounded-full bg-[var(--color-bg-alt)]">
              Market Pulse
            </span>
          </div>
          <button
            type="button"
            onClick={refresh}
            className="text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text)] inline-flex items-center gap-1"
            title="Refresh"
          >
            <RefreshCw size={12} />
            refresh
          </button>
        </div>
      </header>

      <section className="section-padding pt-10">
        <div className="container-main">
          {/* Header */}
          <div className="mb-8">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#ECFDF5] text-[var(--color-green)] text-[11px] font-semibold mb-4">
              <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-green)] animate-pulse" />
              Autonomous · No human in the loop
            </div>
            <h1 className="font-heading text-3xl sm:text-4xl font-extrabold tracking-tight mb-3">
              Market Pulse
            </h1>
            <p className="text-[var(--color-text-secondary)] max-w-2xl leading-relaxed">
              The NEXUS economy runs itself. Every{" "}
              <strong>
                {status
                  ? `${Math.round(status.interval_seconds / 60)} minutes`
                  : "N minutes"}
              </strong>{" "}
              the backend wakes up, asks an{" "}
              <strong>LLM to generate a query</strong> based on live market
              signals (BTC/ETH/SOL 24h change, trending coins, Fear & Greed),
              signs a mandate, hires agents through the orchestrator, settles
              payments via x402 on Kite, and records an audit trail on-chain —
              with nobody at the keyboard. Click any row below to see every
              step with clickable Kitescan transactions.
            </p>
          </div>

          {/* Status strip */}
          {statusStrip}

          {/* Trigger button */}
          <div className="mb-6 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={handleTrigger}
              disabled={triggering}
              className="btn-primary text-sm px-5 py-2.5 inline-flex items-center gap-2"
            >
              {triggering ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  Running autonomous cycle...
                </>
              ) : (
                <>
                  <Play size={14} />
                  Trigger run now
                </>
              )}
            </button>
            <span className="text-[11px] text-[var(--color-text-muted)]">
              Fires one run with a freshly LLM-generated query · rate-limited to 1 / minute
            </span>
          </div>

          {triggerError && (
            <div className="mb-6 flex items-center gap-2 text-sm text-[var(--color-amber)] bg-[#FFFBEB] border border-[#FDE68A] rounded-lg px-4 py-2.5">
              <AlertCircle size={16} />
              {triggerError}
            </div>
          )}

          {/* Runs list */}
          <div className="card p-0 overflow-hidden">
            <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--color-border)]">
              <div className="flex items-center gap-2">
                <Activity size={14} className="text-[var(--color-accent)]" />
                <span className="text-sm font-heading font-bold">
                  Recent runs
                </span>
                <span className="text-xs text-[var(--color-text-muted)]">
                  ({runs.length} of {total})
                </span>
              </div>
              {status?.enabled && status.next_run_at && (
                <div className="text-[11px] text-[var(--color-text-muted)] inline-flex items-center gap-1">
                  <Clock size={11} />
                  next in {countdown(status.next_run_at)}
                </div>
              )}
            </div>

            {loading ? (
              <div className="p-8 text-center text-sm text-[var(--color-text-muted)]">
                <Loader2 size={18} className="animate-spin mx-auto mb-2" />
                Loading runs…
              </div>
            ) : runs.length === 0 ? (
              <div className="p-8 text-center">
                <p className="text-sm text-[var(--color-text-secondary)] mb-2">
                  No autonomous runs yet.
                </p>
                <p className="text-[11px] text-[var(--color-text-muted)]">
                  The first run fires{" "}
                  {status?.initial_delay_seconds
                    ? `~${Math.round(status.initial_delay_seconds / 60)} min`
                    : "shortly"}{" "}
                  after backend boot. Or click <strong>Trigger run now</strong>{" "}
                  above.
                </p>
              </div>
            ) : (
              <ul className="divide-y divide-[var(--color-border)]">
                {runs.map((r) => (
                  <PulseRowExpandable
                    key={r.run_id}
                    run={r}
                    expanded={expandedRunId === r.run_id}
                    detail={details.get(r.run_id) ?? null}
                    detailLoading={detailsLoading === r.run_id}
                    detailError={
                      detailsError && detailsError.id === r.run_id
                        ? detailsError.msg
                        : null
                    }
                    onToggle={() => toggleExpand(r.run_id)}
                  />
                ))}
              </ul>
            )}
          </div>

          {/* Footer line */}
          <p className="text-center text-[11px] text-[var(--color-text-muted)] mt-6">
            Chain ID 2368 · Every run produces a verifiable on-chain audit trail
            on{" "}
            <a
              href="https://testnet.kitescan.ai"
              target="_blank"
              rel="noopener noreferrer"
              className="text-[var(--color-blue)] hover:underline no-underline inline-flex items-center gap-1"
            >
              testnet.kitescan.ai
              <ExternalLink size={10} />
            </a>
          </p>
        </div>
      </section>
    </div>
  );
}

// ======================================================================
// Sub-components
// ======================================================================

function StatBox({ label, value }: { label: string; value: string }) {
  return (
    <div className="card p-4">
      <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] font-semibold mb-1">
        {label}
      </div>
      <div className="font-heading text-xl font-extrabold tabular-nums">
        {value}
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  if (status === "ok")
    return <span className="badge badge-green text-[10px]">ok</span>;
  if (status === "partial")
    return <span className="badge badge-amber text-[10px]">partial</span>;
  return <span className="badge badge-red text-[10px]">error</span>;
}

function SourceBadge({ source }: { source?: PulseQuerySource | null }) {
  const meta = querySourceMeta(source);
  const Icon = meta.icon;
  return (
    <span
      className="inline-flex items-center gap-1 text-[10px] font-semibold px-1.5 py-0.5 rounded"
      style={{ backgroundColor: meta.bg, color: meta.color }}
      title={meta.label}
    >
      <Icon size={10} />
      {meta.label}
    </span>
  );
}

function PulseRowExpandable({
  run,
  expanded,
  detail,
  detailLoading,
  detailError,
  onToggle,
}: {
  run: PulseRun;
  expanded: boolean;
  detail: PulseRunDetail | null;
  detailLoading: boolean;
  detailError: string | null;
  onToggle: () => void;
}) {
  return (
    <li className="hover:bg-[var(--color-bg-alt)]/40 transition-colors">
      {/* Row summary (click to toggle) */}
      <button
        type="button"
        onClick={onToggle}
        className="w-full text-left px-5 py-4 cursor-pointer flex items-start gap-3"
      >
        <span className="pt-0.5 shrink-0 text-[var(--color-text-muted)]">
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <StatusBadge status={run.status} />
            <SourceBadge source={run.query_source} />
            {run.trigger_source === "manual" && (
              <span className="text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-[var(--color-bg-alt)] text-[var(--color-text-muted)]">
                manual
              </span>
            )}
            <span className="text-[11px] text-[var(--color-text-muted)]">
              {timeAgo(run.started_at)}
            </span>
          </div>
          <p className="text-sm font-medium text-[var(--color-text)] mb-1">
            {run.query}
          </p>
          {run.summary && (
            <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed line-clamp-2">
              {run.summary}
            </p>
          )}
          {run.error_message && (
            <p className="text-xs text-[var(--color-red)] font-mono mt-1 line-clamp-2">
              {run.error_message}
            </p>
          )}
        </div>
        <div className="text-right shrink-0 text-[11px] text-[var(--color-text-muted)] space-y-0.5">
          <div>{run.agents_involved} agents</div>
          <div className="font-mono tabular-nums text-[var(--color-text)]">
            ${run.total_cost_usdc.toFixed(4)}
          </div>
          <div>{(run.total_time_ms / 1000).toFixed(1)}s</div>
        </div>
      </button>

      {/* Expanded drill-down */}
      {expanded && (
        <div className="px-5 pb-5 pt-1 border-t border-[var(--color-border)] bg-[var(--color-bg-alt)]/30 animate-fade-in">
          {detailLoading ? (
            <div className="py-6 text-center text-xs text-[var(--color-text-muted)]">
              <Loader2 size={16} className="animate-spin inline-block mr-1.5" />
              Loading full details…
            </div>
          ) : detailError ? (
            <div className="py-4 text-xs text-[var(--color-red)] inline-flex items-center gap-2">
              <AlertCircle size={14} />
              {detailError}
            </div>
          ) : (
            <DrillDown run={run} detail={detail} />
          )}
        </div>
      )}
    </li>
  );
}

function DrillDown({
  run,
  detail,
}: {
  run: PulseRun;
  detail: PulseRunDetail | null;
}) {
  // Prefer the live-joined payment_log (has circuit-breaker decisions).
  // Fall back to the persisted run.payments if mandate was purged.
  const paymentLog = detail?.mandate_detail?.payment_log ?? null;
  const paymentsForDisplay = useMemo(() => {
    if (paymentLog && paymentLog.length > 0) {
      return paymentLog.map((p) => ({
        from_agent: p.from_agent || "",
        to_agent: p.to_agent || "",
        amount: typeof p.amount === "number" ? p.amount : 0,
        purpose: "", // mandate log doesn't carry purpose
        tx_hash: p.tx_hash || "",
        status: p.status || "confirmed",
        blocked_reason: p.blocked_reason ?? null,
        timestamp: p.timestamp,
      }));
    }
    return run.payments.map((p) => ({
      ...p,
      blocked_reason: null as string | null,
      timestamp: undefined as string | undefined,
    }));
  }, [paymentLog, run.payments]);

  const mandate = detail?.mandate_detail;
  const audit = detail?.audit_trail_detail;

  return (
    <div className="space-y-5 pt-3">
      {/* Section A: IDs & Timing */}
      <DrillSection title="IDs & Timing">
        <DrillField label="Run ID" value={run.run_id} mono />
        {run.report_id && (
          <DrillField label="Report ID" value={run.report_id} mono />
        )}
        <DrillField label="Started" value={formatUtc(run.started_at)} />
        <DrillField label="Completed" value={formatUtc(run.completed_at)} />
        <DrillField
          label="Duration"
          value={`${(run.total_time_ms / 1000).toFixed(2)}s`}
        />
        <DrillField
          label="Total cost"
          value={`$${run.total_cost_usdc.toFixed(6)} USDC`}
        />
      </DrillSection>

      {/* Section B: Mandate (Verified Intent) */}
      <DrillSection title="Mandate (Verified Intent)">
        {run.mandate_id ? (
          <>
            <DrillField label="Mandate ID" value={run.mandate_id} mono />
            {mandate ? (
              <>
                {mandate.context_hash && (
                  <DrillField
                    label="Context hash"
                    value={mandate.context_hash}
                    mono
                  />
                )}
                {typeof mandate.total_budget === "number" && (
                  <DrillField
                    label="Budget"
                    value={`$${mandate.total_budget.toFixed(6)} — spent $${(mandate.cumulative_spent ?? 0).toFixed(6)}, remaining $${(mandate.budget_remaining ?? 0).toFixed(6)}`}
                  />
                )}
                {typeof mandate.max_per_tx === "number" && (
                  <DrillField
                    label="Max per tx"
                    value={`$${mandate.max_per_tx.toFixed(6)}`}
                  />
                )}
                {mandate.expires_at && (
                  <DrillField label="Expires" value={formatUtc(mandate.expires_at)} />
                )}
                {mandate.signer_address && (
                  <DrillFieldHashLink
                    label="Signer"
                    value={mandate.signer_address}
                    kind="address"
                  />
                )}
                {mandate.signature && mandate.signature !== "unsigned" && (
                  <DrillFieldHashLink
                    label="ECDSA signature"
                    value={mandate.signature}
                    kind="none"
                  />
                )}
                {mandate.signature === "unsigned" && (
                  <div className="text-[11px] text-[var(--color-amber)] pt-1">
                    <ShieldCheck size={11} className="inline mr-1" />
                    Unsigned (no deployer key in this env) — chain writes still fire
                    but signature validation is skipped.
                  </div>
                )}
                {mandate.status && (
                  <DrillField label="Mandate status" value={mandate.status} />
                )}
                {mandate.allowed_agents && mandate.allowed_agents.length > 0 && (
                  <DrillField
                    label="Allowed agents"
                    value={mandate.allowed_agents.join(", ")}
                  />
                )}
              </>
            ) : (
              <div className="text-[11px] text-[var(--color-text-muted)] italic">
                Mandate no longer in memory (older than retention window).
                ID persisted above; detailed signature/payment-log unavailable
                for this run.
              </div>
            )}
          </>
        ) : (
          <div className="text-[11px] text-[var(--color-text-muted)] italic">
            No mandate (chain offline during this run).
          </div>
        )}
      </DrillSection>

      {/* Section C: Individual x402 payments */}
      <DrillSection title={`x402 payments (${paymentsForDisplay.length})`}>
        {paymentsForDisplay.length === 0 ? (
          <div className="text-[11px] text-[var(--color-text-muted)] italic">
            No settled payments on this run.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="text-left text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] border-b border-[var(--color-border)]">
                  <th className="py-1.5 pr-3 font-semibold">From → To</th>
                  <th className="py-1.5 pr-3 font-semibold">Purpose</th>
                  <th className="py-1.5 pr-3 font-semibold text-right">
                    Amount
                  </th>
                  <th className="py-1.5 pr-3 font-semibold">Status</th>
                  <th className="py-1.5 font-semibold">Tx hash</th>
                </tr>
              </thead>
              <tbody>
                {paymentsForDisplay.map((p, i) => (
                  <tr
                    key={`${p.tx_hash}-${i}`}
                    className="border-b border-[var(--color-border)] last:border-0"
                  >
                    <td className="py-2 pr-3 align-top">
                      <div className="font-medium text-[var(--color-text)]">
                        {p.from_agent || "—"}
                      </div>
                      <div className="text-[var(--color-text-muted)]">
                        → {p.to_agent || "—"}
                      </div>
                    </td>
                    <td className="py-2 pr-3 align-top text-[var(--color-text-secondary)]">
                      {p.purpose || "—"}
                    </td>
                    <td className="py-2 pr-3 align-top text-right font-mono tabular-nums text-[var(--color-accent)] font-semibold">
                      ${p.amount.toFixed(6)}
                    </td>
                    <td className="py-2 pr-3 align-top">
                      {p.status === "confirmed" || p.status === "success" ? (
                        <CheckCircle2
                          size={12}
                          className="inline text-[var(--color-green)] mr-1"
                        />
                      ) : (
                        <XCircle
                          size={12}
                          className="inline text-[var(--color-red)] mr-1"
                        />
                      )}
                      <span className="text-[var(--color-text-muted)]">
                        {p.status}
                      </span>
                      {p.blocked_reason && (
                        <div className="text-[var(--color-red)] mt-0.5">
                          {p.blocked_reason}
                        </div>
                      )}
                    </td>
                    <td className="py-2 align-top max-w-[360px]">
                      {p.tx_hash ? (
                        <HashLink value={p.tx_hash} kind="tx" />
                      ) : (
                        <span className="text-[var(--color-text-muted)]">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </DrillSection>

      {/* Section D: Audit Trail */}
      <DrillSection title="Audit Trail">
        {run.audit_tx_hash ? (
          <>
            <DrillFieldHashLink
              label="On-chain tx"
              value={run.audit_tx_hash}
              kind="tx"
            />
            {audit?.trail_id && (
              <DrillField label="Trail ID" value={audit.trail_id} mono />
            )}
            {audit?.traceability_hash && (
              <DrillFieldHashLink
                label="Traceability hash"
                value={audit.traceability_hash}
                kind="none"
              />
            )}
            {audit?.report_hash && (
              <DrillFieldHashLink
                label="Report hash"
                value={audit.report_hash}
                kind="none"
              />
            )}
          </>
        ) : (
          <div className="text-[11px] text-[var(--color-text-muted)] italic">
            No on-chain audit trail (chain offline during this run or run failed).
          </div>
        )}
      </DrillSection>
    </div>
  );
}

function DrillSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <h3 className="text-[10px] uppercase tracking-wider font-bold text-[var(--color-text-muted)] mb-2">
        {title}
      </h3>
      <div className="space-y-1.5">{children}</div>
    </div>
  );
}

function DrillField({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-start gap-3 text-[11px]">
      <span className="text-[var(--color-text-muted)] w-28 shrink-0 uppercase tracking-wider text-[10px] pt-0.5">
        {label}
      </span>
      <span
        className={`min-w-0 flex-1 break-all ${mono ? "font-mono" : ""} text-[var(--color-text)]`}
      >
        {value}
      </span>
    </div>
  );
}

function DrillFieldHashLink({
  label,
  value,
  kind,
}: {
  label: string;
  value: string;
  kind: "tx" | "address" | "passport" | "none";
}) {
  return (
    <div className="flex items-start gap-3 text-[11px]">
      <span className="text-[var(--color-text-muted)] w-28 shrink-0 uppercase tracking-wider text-[10px] pt-1">
        {label}
      </span>
      <div className="min-w-0 flex-1">
        <HashLink value={value} kind={kind} />
      </div>
    </div>
  );
}

// ======================================================================
// Default export (wrapped in WebSocketProvider so events arrive live)
// ======================================================================

export default function PulsePage() {
  return (
    <WebSocketProvider>
      <PulseInner />
    </WebSocketProvider>
  );
}

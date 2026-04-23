"use client";

/**
 * /pulse — Market Pulse public page.
 *
 * Shows autonomous runs: every N minutes the backend wakes itself up, picks
 * a query from the watchlist, and drives it through the full orchestrator
 * (mandate → x402 payment → audit trail) with no human involvement. Every
 * row here has a clickable Kitescan tx — live on-chain proof.
 *
 * Judges bookmark this URL. New runs arrive via WebSocket event
 * `pulse_run_completed` and the row list re-fetches on a 15s timer as a
 * fallback.
 */

import { useEffect, useMemo, useState } from "react";
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
} from "lucide-react";

import {
  getPulseRuns,
  getPulseStatus,
  triggerPulse,
  type PulseRun,
  type PulseStatus,
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
  const okRuns = runs.filter((r) => r.status === "ok");
  if (okRuns.length === 0) return "—";
  const total = okRuns.reduce((a, r) => a + (r.total_cost_usdc || 0), 0);
  return `$${(total / okRuns.length).toFixed(4)}`;
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

  const { events } = useWebSocketContext();

  // --- Fetch runs + status every 15s and on mount ---
  const refresh = async () => {
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
  };

  useEffect(() => {
    refresh();
    const int = setInterval(refresh, 15000);
    return () => clearInterval(int);
  }, []);

  // --- Countdown re-render every second (no data fetch) ---
  useEffect(() => {
    const int = setInterval(() => setTickTs(Date.now()), 1000);
    return () => clearInterval(int);
  }, []);

  // --- Refresh when a pulse_run_completed event arrives over WS ---
  useEffect(() => {
    if (events.length === 0) return;
    const latest = events[0];
    if (
      latest.event === "pulse_run_completed" ||
      latest.event === "pulse_run_failed"
    ) {
      // Slight debounce — the DB row is written before the WS event fires
      // so this is safe, but give it a beat for any eventual consistency.
      setTimeout(refresh, 500);
    }
  }, [events]);

  const handleTrigger = async () => {
    if (triggering) return;
    setTriggering(true);
    setTriggerError(null);
    try {
      const res = await triggerPulse();
      if ("error" in res) {
        setTriggerError(res.message || "Trigger rate-limited. Try again in a moment.");
      } else {
        // run persisted — it'll show up via refresh() called below
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
    // tickTs in the dep ensures the countdown re-renders each second
    void tickTs;
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
              <strong>{status ? `${Math.round(status.interval_seconds / 60)} minutes` : "N minutes"}</strong>{" "}
              the backend wakes up, picks a query from its watchlist, signs a
              mandate, hires agents through the orchestrator, settles payments
              via x402 on Kite, and records an audit trail on-chain — with
              nobody at the keyboard. Every row below is a real autonomous run
              with a real on-chain transaction hash.
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
              Fires one run immediately · rate-limited to 1 / minute
            </span>
          </div>

          {triggerError && (
            <div className="mb-6 flex items-center gap-2 text-sm text-[var(--color-amber)] bg-[#FFFBEB] border border-[#FDE68A] rounded-lg px-4 py-2.5">
              <AlertCircle size={16} />
              {triggerError}
            </div>
          )}

          {/* Runs table */}
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
                  <PulseRow key={r.run_id} run={r} />
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

function PulseRow({ run }: { run: PulseRun }) {
  const statusBadge =
    run.status === "ok" ? (
      <span className="badge badge-green text-[10px]">ok</span>
    ) : run.status === "partial" ? (
      <span className="badge badge-amber text-[10px]">partial</span>
    ) : (
      <span className="badge badge-red text-[10px]">error</span>
    );

  const triggerBadge =
    run.trigger_source === "manual" ? (
      <span className="text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-[var(--color-bg-alt)] text-[var(--color-text-muted)]">
        manual
      </span>
    ) : null;

  return (
    <li className="px-5 py-4 hover:bg-[var(--color-bg-alt)]/40 transition-colors">
      <div className="flex items-start justify-between gap-4 mb-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1">
            {statusBadge}
            {triggerBadge}
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
      </div>
      {run.audit_tx_hash && (
        <div className="flex items-center gap-2 pt-2">
          <span className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] shrink-0">
            audit tx
          </span>
          <HashLink value={run.audit_tx_hash} kind="tx" />
        </div>
      )}
    </li>
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

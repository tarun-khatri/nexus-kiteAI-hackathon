"use client";

/**
 * InlineDemo — the "try it live" section on the landing page.
 *
 * Judge flow: land on page → click a preset pill → watch the live activity
 * strip tick through discovery → mandate → payment → work → audit → see a
 * compact report card with a clickable tx hash, all without leaving the
 * landing page.
 *
 * Reuses the shared WebSocketProvider (so events don't fight the rest of
 * the app), the HashLink primitive (no truncation), and the same submitQuery
 * helper the dashboard uses.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Search,
  Play,
  Loader2,
  ArrowRight,
  Sparkles,
  AlertCircle,
  CheckCircle2,
  XCircle,
  Fingerprint,
  CreditCard,
  ShieldCheck,
  Brain,
  FileCheck2,
  Coins,
  Activity,
} from "lucide-react";
import {
  submitQuery,
  getExampleQueries,
  type Report,
} from "@/lib/api";
import { useWebSocketContext } from "@/hooks/WebSocketProvider";
import { HashLink } from "@/components/ui/HashLink";

const FALLBACK_PRESETS = [
  "Top DeFi protocols by TVL",
  "Is BTC bullish or bearish right now",
  "Rug check on 0xdAC17F958D2ee523a2206206994597C13D831ec7",
  "Latest Solana memecoins trending",
];

// Map event types → icon + color for the live strip
const EVENT_META: Record<
  string,
  { icon: typeof Search; color: string; bg: string; label: string }
> = {
  agent_discovery: { icon: Brain, color: "#2563EB", bg: "#EFF6FF", label: "Agent Discovery" },
  agent_selected: { icon: Sparkles, color: "#2563EB", bg: "#EFF6FF", label: "Agents Selected" },
  mandate_created: { icon: Fingerprint, color: "#7C3AED", bg: "#F5F3FF", label: "Mandate Signed" },
  work_started: { icon: Play, color: "#D97706", bg: "#FFFBEB", label: "Work Started" },
  work_completed: { icon: CheckCircle2, color: "#16A34A", bg: "#ECFDF5", label: "Work Completed" },
  work_failed: { icon: XCircle, color: "#DC2626", bg: "#FEF2F2", label: "Work Failed" },
  payment_sent: { icon: CreditCard, color: "#E86F2C", bg: "#FEF3E8", label: "Payment Sent" },
  payment_confirmed: { icon: Coins, color: "#16A34A", bg: "#ECFDF5", label: "Payment Confirmed" },
  circuit_breaker_approved: { icon: ShieldCheck, color: "#16A34A", bg: "#ECFDF5", label: "Circuit Breaker Approved" },
  circuit_breaker_blocked: { icon: ShieldCheck, color: "#DC2626", bg: "#FEF2F2", label: "Circuit Breaker Blocked" },
  audit_started: { icon: FileCheck2, color: "#D97706", bg: "#FFFBEB", label: "Audit Started" },
  audit_completed: { icon: FileCheck2, color: "#16A34A", bg: "#ECFDF5", label: "Audit Completed" },
  audit_trail_recorded: { icon: Fingerprint, color: "#7C3AED", bg: "#F5F3FF", label: "Audit Trail Recorded" },
  report_completed: { icon: CheckCircle2, color: "#16A34A", bg: "#ECFDF5", label: "Report Completed" },
};

function formatPreset(q: string): string {
  // Snip to ~60 chars so pills don't wrap ugly
  return q.length > 62 ? q.slice(0, 60).trim() + "…" : q;
}

export function InlineDemo() {
  const [query, setQuery] = useState("");
  const [running, setRunning] = useState(false);
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [presets, setPresets] = useState<string[]>(FALLBACK_PRESETS);
  const [queryStartTs, setQueryStartTs] = useState<number | null>(null);

  const { events, connected } = useWebSocketContext();
  const stripEndRef = useRef<HTMLDivElement>(null);
  const router = useRouter();

  // Stash the full report object in sessionStorage so the dashboard can
  // render it when the judge clicks "Open full report". We use the full
  // report_id as the key; the dashboard reads it on mount.
  const openFullReport = () => {
    if (!report?.report_id) return;
    try {
      sessionStorage.setItem(
        `nexus:report:${report.report_id}`,
        JSON.stringify(report),
      );
    } catch {
      // storage full / disabled — dashboard will just show empty state
    }
    router.push(`/dashboard?report=${encodeURIComponent(report.report_id)}`);
  };

  // Load preset queries from backend
  useEffect(() => {
    getExampleQueries(8)
      .then((res) => {
        const queries = (res.examples || [])
          .map((e) => e.query)
          .filter((q) => q && q.length > 0)
          .slice(0, 4);
        if (queries.length > 0) setPresets(queries);
      })
      .catch(() => {
        // keep fallback
      });
  }, []);

  // Events for the current run only (timestamp >= query start)
  const liveEvents = useMemo(() => {
    if (!queryStartTs) return [];
    return events
      .filter((e) => {
        const t = new Date(e.timestamp).getTime();
        return !isNaN(t) && t >= queryStartTs - 1000; // small slack
      })
      .slice(0, 12)
      .reverse(); // oldest-first in the strip
  }, [events, queryStartTs]);

  // Auto-scroll live strip
  useEffect(() => {
    if (liveEvents.length > 0) {
      stripEndRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [liveEvents.length]);

  const run = async (q?: string) => {
    const actualQuery = (q ?? query).trim();
    if (!actualQuery || running) return;

    setQuery(actualQuery);
    setRunning(true);
    setError(null);
    setReport(null);
    setQueryStartTs(Date.now());

    try {
      const result = await submitQuery(actualQuery);
      if (result.error_code === "not_in_scope") {
        setError(
          "This demo only answers crypto queries — try one of the suggestions below.",
        );
        setReport(null);
      } else if (result.error_code === "no_agent_available") {
        setError(
          "No agent in the marketplace can serve this yet. Try one of the presets.",
        );
      } else {
        setReport(result);
      }
    } catch (e: any) {
      setError(e?.message || "Query failed. Is the backend running?");
    } finally {
      setRunning(false);
    }
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !running && query.trim()) {
      run();
    }
  };

  const txHashes = useMemo(() => {
    if (!report) return [];
    return (report.economy_stats?.transactions || [])
      .map((t) => t.tx_hash)
      .filter((h): h is string => !!h);
  }, [report]);

  const auditTxHash =
    (report?.audit_trail as any)?.on_chain_tx_hash ||
    (report?.audit_trail as any)?.tx_hash ||
    null;

  return (
    <section id="demo" className="section-padding bg-[var(--color-bg-alt)]">
      <div className="container-main">
        {/* Header */}
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white border border-[var(--color-border)] text-[11px] font-semibold text-[var(--color-text-secondary)] mb-4">
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                connected ? "bg-[var(--color-green)]" : "bg-[var(--color-text-faint)]"
              }`}
            />
            {connected ? "WebSocket connected" : "Connecting…"}
          </div>
          <h2 className="font-heading text-2xl sm:text-3xl font-bold mb-3">
            Run a real query. Right here.
          </h2>
          <p className="text-[var(--color-text-secondary)] max-w-xl mx-auto">
            Every click below fires a real LLM router, a real on-chain mandate,
            and a real x402 payment on Kite Aero testnet.
          </p>
        </div>

        {/* Query card */}
        <div className="card p-5 sm:p-7 max-w-3xl mx-auto">
          {/* Input row */}
          <div className="flex flex-col sm:flex-row gap-2.5">
            <div className="relative flex-1">
              <Search
                size={16}
                className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]"
              />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={onKeyDown}
                placeholder="Ask anything crypto — token analysis, DeFi yields, rug check…"
                className="input pl-10 text-[15px]"
                disabled={running}
              />
            </div>
            <button
              type="button"
              onClick={() => run()}
              disabled={running || !query.trim()}
              className="btn-primary px-6 py-3 text-base shrink-0"
            >
              {running ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  Running…
                </>
              ) : (
                <>
                  Go
                  <ArrowRight size={16} />
                </>
              )}
            </button>
          </div>

          {/* Preset pills */}
          <div className="mt-4 flex flex-wrap gap-2">
            <span className="text-[11px] text-[var(--color-text-muted)] self-center mr-1 uppercase tracking-wider font-medium">
              Try:
            </span>
            {presets.map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => run(p)}
                disabled={running}
                className="text-xs px-3 py-1.5 rounded-full border border-[var(--color-border)] bg-white hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] text-[var(--color-text-secondary)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {formatPreset(p)}
              </button>
            ))}
          </div>

          {/* Live activity strip */}
          {running && (
            <div className="mt-6 pt-5 border-t border-[var(--color-border)]">
              <div className="flex items-center gap-2 mb-3">
                <Activity size={14} className="text-[var(--color-accent)]" />
                <span className="text-xs font-semibold text-[var(--color-text-secondary)] uppercase tracking-wider">
                  Live activity
                </span>
                <span className="ml-auto text-[11px] text-[var(--color-text-muted)]">
                  {liveEvents.length} events
                </span>
              </div>
              <div className="space-y-1.5 max-h-[180px] overflow-y-auto pr-1">
                {liveEvents.length === 0 ? (
                  <div className="text-xs text-[var(--color-text-muted)] italic py-2">
                    Waiting for first event…
                  </div>
                ) : (
                  liveEvents.map((e, i) => {
                    const meta = EVENT_META[e.event] || {
                      icon: Activity,
                      color: "#555",
                      bg: "#F5F3EF",
                      label: e.event.replace(/_/g, " "),
                    };
                    const Icon = meta.icon;
                    const txHash = e.data?.tx_hash;
                    return (
                      <div
                        key={`${e.timestamp}-${i}`}
                        className="flex items-center gap-2.5 text-xs py-1 animate-fade-in"
                      >
                        <div
                          className="w-6 h-6 rounded-md flex items-center justify-center shrink-0"
                          style={{ backgroundColor: meta.bg }}
                        >
                          <Icon size={12} style={{ color: meta.color }} />
                        </div>
                        <span className="font-medium text-[var(--color-text)] shrink-0">
                          {meta.label}
                        </span>
                        {e.agent && (
                          <span className="text-[var(--color-text-muted)] truncate">
                            · {e.agent}
                          </span>
                        )}
                        {txHash && (
                          <div className="ml-auto flex-1 max-w-[320px]">
                            <HashLink value={txHash} kind="tx" />
                          </div>
                        )}
                      </div>
                    );
                  })
                )}
                <div ref={stripEndRef} />
              </div>
            </div>
          )}

          {/* Error state */}
          {error && !running && (
            <div className="mt-5 pt-5 border-t border-[var(--color-border)] flex items-start gap-2.5 text-sm">
              <AlertCircle
                size={18}
                className="text-[var(--color-amber)] shrink-0 mt-0.5"
              />
              <div>
                <p className="text-[var(--color-text)] font-medium">{error}</p>
                <p className="text-xs text-[var(--color-text-muted)] mt-1">
                  Tip: click one of the preset pills above.
                </p>
              </div>
            </div>
          )}

          {/* Compact report card */}
          {report && !running && (
            <div className="mt-6 pt-5 border-t border-[var(--color-border)] animate-fade-in">
              <div className="flex items-center gap-2 mb-4">
                <CheckCircle2 size={16} className="text-[var(--color-green)]" />
                <span className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-secondary)]">
                  Report · {report.report_id?.slice(0, 8) || "—"}
                </span>
                <button
                  type="button"
                  onClick={openFullReport}
                  className="ml-auto text-xs text-[var(--color-blue)] hover:underline inline-flex items-center gap-1 bg-transparent border-0 cursor-pointer p-0"
                >
                  Open full report
                  <ArrowRight size={12} />
                </button>
              </div>

              {/* Summary */}
              <p className="text-sm text-[var(--color-text)] leading-relaxed mb-4">
                {report.summary || "Query completed."}
              </p>

              {/* Verdict / score strip */}
              <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-xs mb-4">
                {report.verdict && (
                  <div>
                    <span className="text-[var(--color-text-muted)]">Verdict: </span>
                    <strong className="text-[var(--color-text)]">{report.verdict}</strong>
                  </div>
                )}
                {typeof report.score === "number" && (
                  <div>
                    <span className="text-[var(--color-text-muted)]">Score: </span>
                    <strong className="text-[var(--color-text)]">{report.score}/100</strong>
                  </div>
                )}
                {report.confidence && (
                  <div>
                    <span className="text-[var(--color-text-muted)]">Confidence: </span>
                    <strong className="text-[var(--color-text)]">{report.confidence}</strong>
                  </div>
                )}
                <div>
                  <span className="text-[var(--color-text-muted)]">Agents: </span>
                  <strong className="text-[var(--color-text)]">
                    {report.economy_stats?.agents_involved ?? 0}
                  </strong>
                </div>
                <div>
                  <span className="text-[var(--color-text-muted)]">Cost: </span>
                  <strong className="text-[var(--color-text)]">
                    ${(report.economy_stats?.total_cost_usdc ?? 0).toFixed(4)}
                  </strong>
                </div>
                <div>
                  <span className="text-[var(--color-text-muted)]">Time: </span>
                  <strong className="text-[var(--color-text)]">
                    {((report.economy_stats?.total_time_ms ?? 0) / 1000).toFixed(1)}s
                  </strong>
                </div>
              </div>

              {/* On-chain proofs */}
              {(txHashes.length > 0 || auditTxHash) && (
                <div className="space-y-2 pt-3 border-t border-[var(--color-border)]">
                  {txHashes.slice(0, 3).map((h, i) => (
                    <div key={h} className="flex items-center gap-2">
                      <span className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] w-20 shrink-0">
                        Payment {i + 1}
                      </span>
                      <HashLink value={h} kind="tx" />
                    </div>
                  ))}
                  {auditTxHash && (
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] w-20 shrink-0">
                        Audit Trail
                      </span>
                      <HashLink value={auditTxHash} kind="tx" />
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Reassurance caption */}
        <p className="text-center text-[11px] text-[var(--color-text-muted)] mt-5">
          Backed by real mandates + real on-chain transactions · No server-side mocks
        </p>
      </div>
    </section>
  );
}

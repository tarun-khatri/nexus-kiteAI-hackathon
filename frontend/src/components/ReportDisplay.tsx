"use client";

import { useState } from "react";
import type { Report } from "@/lib/api";
import MandateDisplay from "./MandateDisplay";
import AuditTrailDisplay from "./AuditTrailDisplay";
import { DiscoveryPlanView } from "./DiscoveryPlanView";
import { DataHealthBanner } from "./DataHealthBanner";
import { AlertCircle, TrendingUp, Clock, Users, ArrowRightLeft, ChevronRight } from "lucide-react";
import { AgentSourceCards } from "@/components/dashboard/AgentSourceCards";
import { HashLink } from "@/components/ui/HashLink";

const VERDICT_STYLES: Record<string, string> = {
  "Strong Buy":     "bg-emerald-50 text-emerald-700 border-emerald-200",
  "Buy":            "bg-green-50 text-green-700 border-green-200",
  "Neutral":        "bg-gray-50 text-gray-600 border-gray-200",
  "Sell":           "bg-orange-50 text-orange-700 border-orange-200",
  "Strong Sell":    "bg-red-50 text-red-700 border-red-200",
  "Limited Data":   "bg-amber-50 text-amber-700 border-amber-200",
  "Risk: LOW":      "bg-emerald-50 text-emerald-700 border-emerald-200",
  "Risk: MEDIUM":   "bg-amber-50 text-amber-700 border-amber-200",
  "Risk: HIGH":     "bg-red-50 text-red-700 border-red-200",
  "Risk: CRITICAL": "bg-red-100 text-red-800 border-red-300",
};

export function ReportDisplay({ report }: { report: Report }) {
  const r = report as any;

  /* --- Error shapes (new envelope style) --- */
  const errorCode = r.error_code || r.error;
  if (errorCode === "no_agents_available" || errorCode === "no_agent_available") {
    return (
      <div className="space-y-4">
        <div className="card border-l-4 border-l-[var(--color-amber)] p-5">
          <div className="flex items-start gap-3">
            <AlertCircle size={20} className="text-[var(--color-amber)] shrink-0 mt-0.5" />
            <div>
              <h3 className="font-heading text-sm font-semibold text-[var(--color-amber)]">Agent Gap Detected</h3>
              <p className="text-xs text-[var(--color-text-secondary)] mt-1 leading-relaxed">{r.message}</p>
              {r.missing_capabilities?.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-3">
                  {r.missing_capabilities.map((cap: string) => (
                    <span key={cap} className="badge badge-orange text-[10px]">{cap}</span>
                  ))}
                </div>
              )}
              <p className="text-[11px] text-[var(--color-text-muted)] mt-3 pt-3 border-t border-[var(--color-border)]">
                Register an agent with these capabilities via the &quot;+ Register Agent&quot; button.
              </p>
            </div>
          </div>
        </div>
        {r.execution_plan && <DiscoveryPlanView plan={r.execution_plan} />}
      </div>
    );
  }

  if (errorCode === "router_unavailable" || errorCode === "not_in_scope") {
    return (
      <div className="card border-l-4 border-l-[var(--color-amber)] p-5">
        <div className="flex items-start gap-3">
          <AlertCircle size={20} className="text-[var(--color-amber)] shrink-0 mt-0.5" />
          <div>
            <h3 className="font-heading text-sm font-semibold">{errorCode.replace(/_/g, " ")}</h3>
            <p className="text-[11px] text-[var(--color-text-muted)] mt-1">{r.message || r.reasoning || ""}</p>
          </div>
        </div>
      </div>
    );
  }

  if (r.error && r.hint) {
    return (
      <div className="card border-l-4 border-l-[var(--color-amber)] p-5">
        <div className="flex items-start gap-3">
          <AlertCircle size={20} className="text-[var(--color-amber)] shrink-0 mt-0.5" />
          <div>
            <h3 className="font-heading text-sm font-semibold">{r.error}</h3>
            <p className="text-[11px] text-[var(--color-text-muted)] mt-1">{r.hint}</p>
          </div>
        </div>
      </div>
    );
  }

  /* --- Normal report --- */
  const sections = report.sections || {};
  const outputFields = (r.output_fields || {}) as Record<string, any>;

  // Derive a top-line verdict/score/confidence dynamically — only render
  // what some agent actually produced. No hardcoded N/A placeholders.
  const derivedVerdict: string | null =
    outputFields.verdict
    || (outputFields.risk_level ? `Risk: ${outputFields.risk_level}` : null)
    || (outputFields.overall && outputFields.overall.verdict)
    || report.verdict
    || null;
  const derivedScore: number | null =
    typeof outputFields.risk_score === "number" ? outputFields.risk_score
    : typeof outputFields.score === "number" ? outputFields.score
    : typeof outputFields.overall?.score === "number" ? outputFields.overall.score
    : typeof report.score === "number" && report.score > 0 ? report.score
    : null;
  const derivedConfidence: string | null =
    outputFields.confidence
    || outputFields.overall?.confidence
    || (report.confidence && report.confidence !== "N/A" ? report.confidence : null)
    || null;

  const verdictStyle = derivedVerdict
    ? (VERDICT_STYLES[derivedVerdict] || "bg-gray-50 text-gray-600 border-gray-200")
    : null;

  const successCount = Object.values(sections).filter(
    (s: any) => (s as any).status === "success" || !(s as any).status
  ).length;
  const failureCount = Object.values(sections).length - successCount;

  return (
    <div className="space-y-4">
      {/* Verdict + Score (only rendered if some agent produced a verdict/score) */}
      {(derivedVerdict || derivedScore !== null || derivedConfidence) && (
        <div className="flex flex-wrap items-center gap-3">
          {derivedVerdict && (
            <span className={`px-4 py-1.5 rounded-full text-sm font-heading font-semibold border ${verdictStyle}`}>
              {derivedVerdict}
            </span>
          )}
          {derivedScore !== null && (
            <span className="text-xs text-[var(--color-text-muted)]">Score: <strong className="text-[var(--color-text)]">{derivedScore}/100</strong></span>
          )}
          {derivedConfidence && (
            <span className="text-xs text-[var(--color-text-muted)]">Confidence: <strong className="text-[var(--color-text)]">{derivedConfidence}</strong></span>
          )}
        </div>
      )}

      {/* Failure banner when some agents failed */}
      {failureCount > 0 && (
        <div className="card border-l-4 border-l-[var(--color-amber)] p-3">
          <p className="text-xs text-[var(--color-amber)] font-heading font-semibold">
            Partial report: {successCount} agent(s) succeeded, {failureCount} failed
          </p>
          <p className="text-[11px] text-[var(--color-text-muted)] mt-1">
            Expand the failed sections below to see the error from each agent.
          </p>
        </div>
      )}

      {/* Summary */}
      {report.summary && (
        <p className="text-sm text-[var(--color-text-secondary)] leading-relaxed">{report.summary}</p>
      )}

      {/* Data Health */}
      {report.data_sources_status && (
        <DataHealthBanner status={report.data_sources_status} degraded={report.degraded_sources} />
      )}

      {/* Partial report warning */}
      {report.partial && report.missing_capabilities && report.missing_capabilities.length > 0 && (
        <div className="card border-l-4 border-l-[var(--color-amber)] p-4">
          <p className="text-xs font-heading font-semibold text-[var(--color-amber)] mb-1">Partial Report</p>
          <div className="flex flex-wrap gap-1.5">
            {report.missing_capabilities.map((cap) => (
              <span key={cap} className="badge badge-orange text-[9px]">{cap}</span>
            ))}
          </div>
        </div>
      )}

      {/* Agent Source Cards (Perplexity-style citations) */}
      {report.economy_stats?.transactions && report.economy_stats.transactions.length > 0 && (
        <AgentSourceCards
          agents={report.economy_stats.transactions.map((t: any) => ({
            name: t.to || "unknown",
            capability: t.purpose || "work",
            price: t.amount || 0,
            source: t.source || "builtin",
          }))}
          auditScore={(() => {
            // Search all envelope sections for a quality_score in the output.
            for (const sec of Object.values(sections) as any[]) {
              const out = (sec && sec.output) || sec;
              if (out && typeof out === "object" && typeof (out as any).quality_score === "number") {
                return (out as any).quality_score as number;
              }
            }
            return undefined;
          })()}
        />
      )}

      {/* Dynamic sections (collapsible accordions) */}
      <div className="space-y-1">
        {Object.entries(sections).map(([key, section]) => (
          <CollapsibleSection key={key} sectionKey={key} data={section as Record<string, any>} />
        ))}
      </div>

      {/* Economy stats */}
      {report.economy_stats && (
        <div className="flex flex-wrap items-center gap-4 pt-3 border-t border-[var(--color-border)] text-[11px] text-[var(--color-text-muted)]">
          <span className="inline-flex items-center gap-1"><TrendingUp size={12} /> ${report.economy_stats.total_cost_usdc?.toFixed(4)}</span>
          <span className="inline-flex items-center gap-1"><Clock size={12} /> {((report.economy_stats.total_time_ms || 0) / 1000).toFixed(1)}s</span>
          <span className="inline-flex items-center gap-1"><Users size={12} /> {report.economy_stats.agents_involved} agents</span>
          <span className="inline-flex items-center gap-1"><ArrowRightLeft size={12} /> {report.economy_stats.transactions?.length || 0} txns</span>
        </div>
      )}

      {/* On-Chain Proof (collapsible) */}
      {(r.verified_intent || r.audit_trail || r.execution_plan) && (
        <div className="space-y-1">
          <p className="text-[11px] font-medium text-[var(--color-text-muted)] uppercase tracking-wider mb-2 mt-2">
            On-Chain Proof
          </p>
          {r.verified_intent && (
            <CollapsibleWrapper title="Verified Intent Mandate" preview={r.verified_intent.mandate_id || ""}>
              <MandateDisplay mandate={r.verified_intent} />
            </CollapsibleWrapper>
          )}
          {r.audit_trail && (
            <CollapsibleWrapper title="Audit Trail" preview={r.audit_trail.traceability_hash || ""}>
              <AuditTrailDisplay trail={r.audit_trail} />
            </CollapsibleWrapper>
          )}
          {r.execution_plan && (
            <CollapsibleWrapper title="Discovery Plan" preview={`${r.execution_plan.agents_selected?.length || 0} agents`}>
              <DiscoveryPlanView plan={r.execution_plan} />
            </CollapsibleWrapper>
          )}
        </div>
      )}
    </div>
  );
}

/* =============================================
   Dynamic Section Renderer
   Handles ANY agent output shape (DeFi, DEX,
   Security, Analyst, or unknown future agents)
   ============================================= */

function DynamicSection({ sectionKey, data }: { sectionKey: string; data: Record<string, any> }) {
  if (!data || typeof data !== "object") return null;

  const agentName = data.agent || sectionKey;
  const headline = extractHeadline(data);

  const displayEntries = Object.entries(data).filter(
    ([k]) => !["agent", "timestamp", "query", "duration_ms", "data_source_real", "source"].includes(k)
  );

  /* Audit section (special rendering) */
  if (data.quality_score !== undefined) {
    const q = data.quality_score || 0;
    // AuditAgent returns `passed_checks` / `total_checks`. Earlier code also
    // used `checks_passed` / `checks_total` in some serialization paths, so
    // accept either spelling. Fall back to `checks.length` if only the array
    // is present.
    const passed = (
      data.passed_checks ??
      data.checks_passed ??
      (Array.isArray(data.checks) ? data.checks.filter((c: any) => c?.passed).length : undefined) ??
      0
    );
    const total = (
      data.total_checks ??
      data.checks_total ??
      (Array.isArray(data.checks) ? data.checks.length : undefined) ??
      0
    );
    return (
      <div className="card p-4">
        <p className="text-[10px] text-[var(--color-text-muted)] font-medium uppercase tracking-wider mb-1">Quality Audit</p>
        <p className={`font-heading text-xl font-bold ${q >= 70 ? "text-[var(--color-green)]" : "text-[var(--color-red)]"}`}>
          {q}/100
        </p>
        <p className="text-[11px] text-[var(--color-text-muted)] mt-1">
          {passed}/{total} checks passed
        </p>
      </div>
    );
  }

  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-2">
        <p className="text-[10px] text-[var(--color-text-muted)] font-medium uppercase tracking-wider">{formatLabel(sectionKey)}</p>
        <span className="text-[9px] text-[var(--color-text-faint)]">
          {typeof agentName === "string" ? agentName.replace(/^Nexus-/, "").replace(/-v\d+$/, "") : ""}
        </span>
      </div>

      {headline && (
        <p className="font-heading text-base font-semibold text-[var(--color-text)] mb-2">{headline}</p>
      )}

      <div className="space-y-1">
        {displayEntries.slice(0, 6).map(([key, value]) => (
          <MetricRow key={key} label={key} value={value} />
        ))}
        {displayEntries.length > 6 && (
          <p className="text-[10px] text-[var(--color-text-faint)] pt-1">+{displayEntries.length - 6} more fields</p>
        )}
      </div>
    </div>
  );
}

function MetricRow({ label, value }: { label: string; value: any }) {
  if (Array.isArray(value)) {
    return (
      <div className="flex justify-between text-[11px] py-0.5">
        <span className="text-[var(--color-text-muted)]">{formatLabel(label)}</span>
        <span className="text-[var(--color-text-secondary)] font-medium">{value.length} items</span>
      </div>
    );
  }
  if (typeof value === "object" && value !== null) {
    return (
      <div className="flex justify-between text-[11px] py-0.5">
        <span className="text-[var(--color-text-muted)]">{formatLabel(label)}</span>
        <span className="text-[var(--color-text-secondary)]">{Object.keys(value).length} fields</span>
      </div>
    );
  }
  if (typeof value === "boolean") {
    return (
      <div className="flex justify-between text-[11px] py-0.5">
        <span className="text-[var(--color-text-muted)]">{formatLabel(label)}</span>
        <span className={value ? "text-[var(--color-green)] font-medium" : "text-[var(--color-red)] font-medium"}>
          {value ? "Yes" : "No"}
        </span>
      </div>
    );
  }
  if (typeof value === "number") {
    const fmt = Math.abs(value) >= 1_000_000
      ? `$${(value / 1_000_000).toFixed(1)}M`
      : Math.abs(value) >= 1000
        ? `$${(value / 1000).toFixed(1)}K`
        : value % 1 !== 0
          ? value.toFixed(4)
          : String(value);
    return (
      <div className="flex justify-between text-[11px] py-0.5">
        <span className="text-[var(--color-text-muted)]">{formatLabel(label)}</span>
        <span className="font-mono font-medium text-[var(--color-text)]">{fmt}</span>
      </div>
    );
  }
  return (
    <div className="flex justify-between text-[11px] py-0.5 gap-4">
      <span className="text-[var(--color-text-muted)] shrink-0">{formatLabel(label)}</span>
      <span className="text-[var(--color-text-secondary)] text-right break-words min-w-0">{String(value ?? "N/A")}</span>
    </div>
  );
}

function formatLabel(key: string): string {
  // Full label, no truncation. Long identifier keys stay full so users can
  // read every field name; CSS `break-words` handles overflow.
  return key.replace(/_/g, " ").replace(/pct$/i, "%").replace(/usd$/i, " USD").replace(/\b\w/g, (c) => c.toUpperCase());
}

function extractHeadline(data: Record<string, any>): string | null {
  if (data.verdict && typeof data.verdict === "string") return data.verdict;
  if (data.risk_level) return `Risk: ${data.risk_level} (${data.risk_score ?? "?"}/100)`;
  if (data.overall?.verdict) return data.overall.verdict;
  if (data.current_price) return `$${Number(data.current_price).toFixed(4)}`;
  if (data.total_liquidity_usd) return `Liquidity: $${(data.total_liquidity_usd / 1e6).toFixed(1)}M`;
  if (data.pairs_found) return `${data.pairs_found} DEX pairs`;
  if (data.total_protocols) return `${data.total_protocols} protocols`;
  if (data.net_flow) return `Net Flow: ${data.net_flow}`;
  return null;
}

/* =============================================
   Collapsible Section (accordion-style)
   Shows 1-line summary when collapsed,
   full DynamicSection content when expanded.
   ============================================= */

function CollapsibleSection({ sectionKey, data }: { sectionKey: string; data: Record<string, any> }) {
  const [open, setOpen] = useState(false);
  if (!data || typeof data !== "object") return null;

  // Detect new envelope shape: { status, output, agent_name, capability, error_* }
  const isEnvelope = typeof data.status === "string" &&
    ["success", "partial", "failed", "timeout", "unreachable", "invalid_input"].includes(data.status);

  const body = isEnvelope ? (data.output || {}) : data;
  const failed = isEnvelope && data.status !== "success" && data.status !== "partial";
  const agentName = data.agent_name || data.agent || sectionKey;

  const headline = failed
    ? `${String(data.status).toUpperCase()}: ${data.error_message || data.error_code || "unknown error"}`
    : extractHeadline(body || {});

  const isAudit = !failed && body && (body as any).quality_score !== undefined;
  const label = formatLabel(sectionKey);

  return (
    <div className={`border rounded-xl overflow-hidden ${failed ? "border-red-200 bg-red-50/30" : "border-[var(--color-border)]"}`}>
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-[var(--color-bg-alt)] transition-colors"
      >
        <div className="flex items-center gap-2 min-w-0">
          <ChevronRight size={14} className={`text-[var(--color-text-muted)] transition-transform ${open ? "rotate-90" : ""}`} />
          <span className="text-xs font-heading font-semibold">{label}</span>
          {typeof agentName === "string" && (
            <span className="text-[9px] text-[var(--color-text-faint)] truncate max-w-[140px]">
              {agentName.replace(/^Nexus-/, "").replace(/-v\d+$/, "")}
            </span>
          )}
        </div>
        <span className="text-xs shrink-0 ml-3">
          {failed ? (
            <span className="text-[var(--color-red)] font-semibold truncate max-w-[260px] inline-block">
              {String(data.status).toUpperCase()}
            </span>
          ) : isAudit ? (
            <span className={(body as any).quality_score >= 70 ? "text-[var(--color-green)] font-semibold" : "text-[var(--color-red)] font-semibold"}>
              {(body as any).quality_score}/100
            </span>
          ) : (
            <span className="text-[var(--color-text-muted)]">{headline || ""}</span>
          )}
        </span>
      </button>
      {open && (
        <div className="px-4 pb-4 border-t border-[var(--color-border)] animate-fade-in">
          <div className="pt-3">
            {failed ? (
              <div className="text-[12px] leading-relaxed">
                <p className="font-heading text-sm text-[var(--color-red)] mb-1">
                  {String(data.status).toUpperCase()}
                </p>
                {data.error_message && (
                  <p className="text-[var(--color-text-secondary)] mb-1"><strong>Reason:</strong> {data.error_message}</p>
                )}
                {data.error_hint && (
                  <p className="text-[var(--color-text-muted)] mb-1"><strong>Hint:</strong> {data.error_hint}</p>
                )}
                {data.error_code && (
                  <p className="text-[10px] text-[var(--color-text-faint)]">code: <code>{data.error_code}</code></p>
                )}
                {data.payment_tx_hash ? (
                  <div className="mt-2 space-y-1">
                    <p className="text-[10px] text-[var(--color-text-faint)]">
                      Payment was executed on-chain but the agent did not produce usable output. Reputation penalty applied.
                    </p>
                    <HashLink value={data.payment_tx_hash} kind="tx" label="tx" />
                  </div>
                ) : (
                  <p className="text-[10px] text-[var(--color-text-faint)] mt-1">
                    No on-chain payment was made — probe detected the agent was unreachable.
                  </p>
                )}
              </div>
            ) : (
              <DynamicSection sectionKey={sectionKey} data={body as Record<string, any>} />
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* =============================================
   Collapsible Wrapper (for on-chain proof items)
   ============================================= */

function CollapsibleWrapper({ title, preview, children }: { title: string; preview?: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="border border-[var(--color-border)] rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-[var(--color-bg-alt)] transition-colors"
      >
        <div className="flex items-center gap-2">
          <ChevronRight size={14} className={`text-[var(--color-text-muted)] transition-transform ${open ? "rotate-90" : ""}`} />
          <span className="text-xs font-heading font-semibold">{title}</span>
        </div>
        {preview && (
          // Header preview: full value, monospace, one line with horizontal
          // scroll when it overflows — never truncated with "...".
          <span className="text-[10px] font-mono text-[var(--color-text-muted)] ml-3 overflow-x-auto whitespace-nowrap max-w-[260px] no-scrollbar-thumb">
            {preview}
          </span>
        )}
      </button>
      {open && (
        <div className="px-4 pb-4 border-t border-[var(--color-border)] animate-fade-in">
          <div className="pt-3">
            {children}
          </div>
        </div>
      )}
    </div>
  );
}

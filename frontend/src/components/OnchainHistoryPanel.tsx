"use client";

/**
 * OnchainHistoryPanel — renders the list of past payments from the
 * PaymentRouter contract. Served by GET /api/onchain-history, NOT
 * interleaved with the live session feed anymore.
 *
 * Every passport becomes a clickable link to Kitescan. Every payment
 * row shows full UTC timestamp + full mandate id + full amount.
 */

import { useEffect, useState } from "react";
import { getOnchainHistory, type OnchainPayment } from "@/lib/api";
import { HashLink } from "@/components/ui/HashLink";
import { ArrowRight, RefreshCw, Loader2 } from "lucide-react";

function formatUtc(isoOrUnix: string | null | undefined, unix: number): string {
  if (isoOrUnix) {
    // Convert ISO to "YYYY-MM-DD HH:MM:SS UTC"
    const d = new Date(isoOrUnix);
    if (!isNaN(d.getTime())) {
      return d.toISOString().replace("T", " ").slice(0, 19) + " UTC";
    }
  }
  if (unix > 0) {
    const d = new Date(unix * 1000);
    return d.toISOString().replace("T", " ").slice(0, 19) + " UTC";
  }
  return "—";
}

export function OnchainHistoryPanel() {
  const [payments, setPayments] = useState<OnchainPayment[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getOnchainHistory(100);
      if (res.error) {
        setError(res.error);
        setPayments([]);
      } else {
        setPayments(res.payments || []);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setPayments([]);
    }
    setLoading(false);
  };

  useEffect(() => {
    load();
  }, []);

  if (loading && payments === null) {
    return (
      <div className="flex items-center justify-center py-12 text-sm text-[var(--color-text-muted)]">
        <Loader2 size={16} className="animate-spin mr-2" />
        Loading on-chain history from Kite…
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between pb-2 border-b border-[var(--color-border)]">
        <p className="text-xs text-[var(--color-text-muted)]">
          {payments?.length ?? 0} historical payments from{" "}
          <a
            href="https://testnet.kitescan.ai/address/0xd76ea536704252DeD9602eCd549F776aD302c73C"
            target="_blank"
            rel="noopener noreferrer"
            className="text-[var(--color-blue)] hover:underline no-underline"
          >
            PaymentRouter contract
          </a>
        </p>
        <button
          type="button"
          onClick={load}
          disabled={loading}
          className="inline-flex items-center gap-1 text-[11px] text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
          title="Refresh"
        >
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="card border-l-4 border-l-[var(--color-red)] p-3 text-xs">
          <strong>Error:</strong> {error}
        </div>
      )}

      {payments && payments.length === 0 && !error && (
        <p className="text-sm text-[var(--color-text-muted)] text-center py-8">
          No on-chain payments yet.
        </p>
      )}

      {payments?.map((p) => (
        <div
          key={`${p.index}-${p.timestamp_unix}`}
          className="border border-[var(--color-border)] rounded-lg p-3 space-y-2 bg-white"
        >
          <div className="flex items-center justify-between gap-3 text-[11px]">
            <span className="font-mono text-[var(--color-text-faint)]">
              #{p.index}
            </span>
            <span className="font-mono text-[var(--color-text-muted)]">
              {formatUtc(p.timestamp_iso, p.timestamp_unix)}
            </span>
          </div>

          <div className="flex items-start gap-2 text-xs">
            <div className="flex-1 min-w-0">
              <p className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">
                From
              </p>
              <p className="font-medium mb-1">
                {p.from_agent || <span className="italic text-[var(--color-text-faint)]">unknown agent</span>}
              </p>
              <HashLink value={p.from_passport} kind="address" />
            </div>
            <ArrowRight size={14} className="text-[var(--color-text-muted)] mt-4 shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">
                To
              </p>
              <p className="font-medium mb-1">
                {p.to_agent || <span className="italic text-[var(--color-text-faint)]">unknown agent</span>}
              </p>
              <HashLink value={p.to_passport} kind="address" />
            </div>
          </div>

          <div className="flex items-center justify-between gap-3 pt-1.5 border-t border-[var(--color-border)] text-[11px]">
            <span className="font-mono font-semibold text-[var(--color-text)]">
              ${p.amount_usdc.toFixed(6)}
            </span>
            <span className="text-[var(--color-text-muted)]">
              purpose: <code className="font-mono">{p.purpose || "—"}</code>
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}

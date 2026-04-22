"use client";

import { Stamp, CheckCircle2 } from "lucide-react";
import { HashLink } from "@/components/ui/HashLink";

interface MandatePaymentLogEntry {
  to_agent?: string;
  amount?: number;
  purpose?: string;
  tx_hash?: string;
  status?: string;
  error_code?: string | null;
  error_message?: string | null;
  timestamp?: string;
}

interface MandateInfo {
  mandate_id?: string;
  context_hash?: string;
  total_budget?: number;
  total_spent?: number;
  budget_remaining?: number;
  max_per_tx?: number;
  signature?: string;
  signer?: string;
  status?: string;
  expires_at?: string;
  payments?: number;
  payment_log?: MandatePaymentLogEntry[];
}

const STATUS_STYLE: Record<string, string> = {
  active: "badge-green",
  completed: "badge-blue",
  expired: "badge-gray",
  breached: "badge-red",
};

export default function MandateDisplay({ mandate }: { mandate: MandateInfo }) {
  if (!mandate?.mandate_id) return null;

  const budgetPct = mandate.total_budget
    ? Math.min(100, ((mandate.total_spent || 0) / mandate.total_budget) * 100)
    : 0;
  const isSigned = mandate.signature && mandate.signature !== "unsigned";
  const paymentLog = mandate.payment_log || [];

  return (
    <div className="card border-l-4 border-l-[var(--color-accent)] p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Stamp size={16} className="text-[var(--color-accent)]" />
          <h4 className="font-heading text-sm font-semibold">Verified Intent Mandate</h4>
        </div>
        <span className={`badge ${STATUS_STYLE[mandate.status || "active"] || "badge-gray"}`}>
          {mandate.status || "active"}
        </span>
      </div>

      <div className="space-y-3">
        <div>
          <p className="text-[10px] text-[var(--color-text-muted)] font-medium uppercase tracking-wider mb-1">Mandate ID</p>
          <HashLink value={mandate.mandate_id} kind="mandate" />
        </div>

        <div>
          <p className="text-[10px] text-[var(--color-text-muted)] font-medium uppercase tracking-wider mb-1">Context Hash (sha256 of query)</p>
          <HashLink value={mandate.context_hash} kind="none" />
        </div>

        {isSigned && mandate.signer && (
          <div>
            <p className="text-[10px] text-[var(--color-text-muted)] font-medium uppercase tracking-wider mb-1 inline-flex items-center gap-1">
              <CheckCircle2 size={11} className="text-[var(--color-green)]" />
              ECDSA Signer
            </p>
            <HashLink value={mandate.signer} kind="address" />
          </div>
        )}

        {mandate.signature && isSigned && (
          <div>
            <p className="text-[10px] text-[var(--color-text-muted)] font-medium uppercase tracking-wider mb-1">Signature</p>
            <HashLink value={mandate.signature} kind="none" />
          </div>
        )}
      </div>

      <div>
        <div className="flex items-center justify-between mb-1.5">
          <p className="text-[10px] text-[var(--color-text-muted)] font-medium uppercase tracking-wider">Budget Used</p>
          <p className="text-xs font-mono font-medium">${(mandate.total_spent || 0).toFixed(4)} / ${(mandate.total_budget || 0).toFixed(4)}</p>
        </div>
        <div className="w-full h-2 bg-[var(--color-bg-alt)] rounded-full overflow-hidden">
          <div className="h-full rounded-full transition-all duration-500" style={{ width: `${budgetPct}%`, background: `linear-gradient(90deg, var(--color-accent), var(--color-amber))` }} />
        </div>
      </div>

      <div className="flex flex-wrap gap-x-6 gap-y-1 text-[11px] text-[var(--color-text-muted)]">
        <span>Max/TX: <strong className="text-[var(--color-text)]">${(mandate.max_per_tx || 0).toFixed(4)}</strong></span>
        <span>Payments: <strong className="text-[var(--color-text)]">{mandate.payments || 0}</strong></span>
        {mandate.expires_at && <span>Expires: <strong className="text-[var(--color-text)]">{mandate.expires_at}</strong></span>}
      </div>

      {paymentLog.length > 0 && (
        <div className="pt-2 border-t border-[var(--color-border)] space-y-2">
          <p className="text-[10px] text-[var(--color-text-muted)] font-medium uppercase tracking-wider">
            Payment log ({paymentLog.length})
          </p>
          {paymentLog.map((p, idx) => {
            const isOK = (p.status || "succeeded") === "succeeded";
            return (
              <div
                key={idx}
                className={`rounded-md p-2 space-y-1 text-[11px] ${
                  isOK
                    ? "bg-[var(--color-bg-alt)]"
                    : "bg-red-50 border border-red-200"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium break-all">{p.to_agent || "?"}</span>
                  <span className="font-mono font-medium shrink-0">
                    ${typeof p.amount === "number" ? p.amount.toFixed(4) : "?"}
                  </span>
                </div>
                <div className="flex items-center justify-between gap-2 text-[var(--color-text-muted)]">
                  <span>
                    purpose: <code className="font-mono">{p.purpose || "—"}</code>
                  </span>
                  <span
                    className={
                      isOK
                        ? "text-[var(--color-green)]"
                        : "text-[var(--color-red)]"
                    }
                  >
                    {p.status || "succeeded"}
                  </span>
                </div>
                {p.tx_hash && <HashLink value={p.tx_hash} kind="tx" label="tx" />}
                {p.error_message && (
                  <p className="text-[10px] text-[var(--color-red)] break-words">
                    error: {p.error_message}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

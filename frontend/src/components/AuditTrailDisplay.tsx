"use client";

import { useEffect, useState, useRef } from "react";
import { FileCheck, Loader2, AlertTriangle } from "lucide-react";
import { getAuditTrail } from "@/lib/api";
import { useWebSocketContext } from "@/hooks/WebSocketProvider";
import { HashLink } from "@/components/ui/HashLink";

interface AuditTrailInfo {
  trail_id?: string;
  traceability_hash?: string;
  report_hash?: string;
  on_chain_tx_hash?: string | null;
  explorer_url?: string | null;
  chain_status?: "pending" | "recorded" | string;
}

export default function AuditTrailDisplay({ trail }: { trail: AuditTrailInfo }) {
  /*
   * The audit-trail chain write runs in the background (~20-30s). We upgrade
   * the UI from "pending" → "recorded" via two paths, whichever fires first:
   *
   *   1. WebSocket `audit_trail_recorded` event w/ on_chain_tx_hash set
   *      (via the shared WebSocketProvider, not a per-component socket).
   *   2. Polling `/api/audit-trail/{trail_id}` every 3s for up to ~2 min.
   *
   * If neither lands within the polling window, we render a "stalled" card
   * so the user sees an honest failure state instead of a forever-spinner.
   */
  const { events } = useWebSocketContext();
  const [liveTrail, setLiveTrail] = useState<AuditTrailInfo>(trail);
  const [exhausted, setExhausted] = useState(false);
  const pollCountRef = useRef(0);
  const MAX_POLLS = 40;

  // Reset state when a new trail arrives (e.g. user submits a new query).
  useEffect(() => {
    setLiveTrail(trail);
    setExhausted(false);
    pollCountRef.current = 0;
  }, [trail?.trail_id, trail?.traceability_hash]);

  // Path 1: WebSocket upgrade. Watch the shared events stream for a
  // matching "recorded" event and apply it immediately.
  useEffect(() => {
    if (liveTrail.on_chain_tx_hash) return;
    if (!liveTrail.trail_id) return;

    const match = events.find(
      (e) =>
        e?.event === "audit_trail_recorded" &&
        e?.data?.trail_id === liveTrail.trail_id &&
        e?.data?.on_chain_tx_hash,
    );
    if (match) {
      setLiveTrail((prev) => ({
        ...prev,
        on_chain_tx_hash: match.data.on_chain_tx_hash,
        explorer_url: match.data.explorer_url,
        chain_status: "recorded",
      }));
    }
  }, [events, liveTrail.trail_id, liveTrail.on_chain_tx_hash]);

  // Path 2: polling fallback.
  useEffect(() => {
    if (liveTrail.on_chain_tx_hash) return;
    if (!liveTrail.trail_id) return;
    if (exhausted) return;

    let cancelled = false;
    let timerId: ReturnType<typeof setTimeout> | null = null;

    const poll = async () => {
      if (cancelled) return;
      if (pollCountRef.current >= MAX_POLLS) {
        setExhausted(true);
        return;
      }
      pollCountRef.current += 1;
      try {
        const fresh = await getAuditTrail(liveTrail.trail_id!);
        if (cancelled) return;
        if (fresh && fresh.on_chain_tx_hash) {
          setLiveTrail((prev) => ({
            ...prev,
            on_chain_tx_hash: fresh.on_chain_tx_hash,
            explorer_url: fresh.explorer_url,
            chain_status: "recorded",
          }));
          return;
        }
      } catch {
        // transient failure; retry
      }
      timerId = setTimeout(poll, 3000);
    };

    timerId = setTimeout(poll, 2000);
    return () => {
      cancelled = true;
      if (timerId) clearTimeout(timerId);
    };
  }, [liveTrail.trail_id, liveTrail.on_chain_tx_hash, exhausted]);

  if (!liveTrail?.traceability_hash) return null;

  const hasChainHash = Boolean(liveTrail.on_chain_tx_hash);
  const isPending = !hasChainHash && !exhausted && (liveTrail.chain_status === "pending" || !liveTrail.chain_status);

  return (
    <div className="card border-l-4 border-l-[var(--color-blue)] p-5 space-y-4">
      <div className="flex items-center gap-2">
        <FileCheck size={16} className="text-[var(--color-blue)]" />
        <h4 className="font-heading text-sm font-semibold">On-Chain Audit Trail</h4>
      </div>

      <div className="space-y-3">
        {liveTrail.trail_id && (
          <div>
            <p className="text-[10px] text-[var(--color-text-muted)] font-medium uppercase tracking-wider mb-1">Trail ID</p>
            <HashLink value={liveTrail.trail_id} kind="none" />
          </div>
        )}
        <div>
          <p className="text-[10px] text-[var(--color-text-muted)] font-medium uppercase tracking-wider mb-1">Traceability Hash</p>
          <HashLink value={liveTrail.traceability_hash} kind="none" />
        </div>
        {liveTrail.report_hash && (
          <div>
            <p className="text-[10px] text-[var(--color-text-muted)] font-medium uppercase tracking-wider mb-1">Report Hash</p>
            <HashLink value={liveTrail.report_hash} kind="none" />
          </div>
        )}
      </div>

      {hasChainHash ? (
        <div>
          <p className="text-[10px] font-medium uppercase tracking-wider mb-1 text-[var(--color-green)]">
            On-chain tx
          </p>
          <HashLink value={liveTrail.on_chain_tx_hash!} kind="tx" />
        </div>
      ) : isPending ? (
        <div className="inline-flex items-center gap-1.5 text-[11px] text-[var(--color-blue)] italic">
          <Loader2 size={12} className="animate-spin" />
          Writing to Kite chain… (tx link will appear here, typically 20-30s)
        </div>
      ) : exhausted ? (
        <div className="rounded-md bg-amber-50 border border-amber-200 p-3 space-y-2">
          <p className="inline-flex items-center gap-1.5 text-[11px] font-medium text-[var(--color-amber)]">
            <AlertTriangle size={12} />
            Chain write stalled — the audit-trail tx hasn't landed in the expected time window.
          </p>
          <p className="text-[10px] text-[var(--color-text-muted)] break-words">
            Off-chain traceability hash above is still a valid cryptographic fingerprint of this
            query + its result. You can retry the on-chain record by reloading
            <code className="font-mono px-1"> /api/audit-trail/{liveTrail.trail_id}</code> — if
            the tx eventually lands, this card will upgrade automatically.
          </p>
          <button
            type="button"
            onClick={() => {
              pollCountRef.current = 0;
              setExhausted(false);
            }}
            className="text-[11px] px-2 py-1 rounded border border-[var(--color-amber)] text-[var(--color-amber)] hover:bg-amber-100"
          >
            Retry polling
          </button>
        </div>
      ) : (
        <p className="text-[11px] text-[var(--color-text-muted)] italic">
          Local hash only — on-chain write not attempted.
        </p>
      )}
    </div>
  );
}

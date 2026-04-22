"use client";

import { useState } from "react";
import { updateGovernance } from "@/lib/api";
import { Settings, CheckCircle2 } from "lucide-react";

export function GovernancePanel({ currentRules }: { currentRules?: Record<string, number> }) {
  const [maxPerTx, setMaxPerTx] = useState(String(currentRules?.max_spend_per_tx ?? "0.001"));
  const [maxPerDay, setMaxPerDay] = useState(String(currentRules?.max_spend_per_day ?? "0.01"));
  const [updating, setUpdating] = useState(false);
  const [message, setMessage] = useState("");

  const handleUpdate = async () => {
    setUpdating(true);
    setMessage("");
    try {
      await updateGovernance({
        max_spend_per_tx: parseFloat(maxPerTx),
        max_spend_per_day: parseFloat(maxPerDay),
      });
      setMessage("Updated on-chain");
      setTimeout(() => setMessage(""), 3000);
    } catch {
      setMessage("Update failed");
    }
    setUpdating(false);
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 mb-1">
        <Settings size={14} className="text-[var(--color-text-muted)]" />
        <h3 className="font-heading text-xs font-semibold text-[var(--color-text-secondary)] uppercase tracking-wider">Governance</h3>
      </div>

      <div className="space-y-2">
        <div>
          <label className="text-[11px] font-medium text-[var(--color-text-muted)] mb-1 block">Max per transaction (USDC)</label>
          <input
            type="number"
            value={maxPerTx}
            onChange={(e) => setMaxPerTx(e.target.value)}
            step="0.0001"
            min="0"
            className="input text-xs py-2"
          />
        </div>
        <div>
          <label className="text-[11px] font-medium text-[var(--color-text-muted)] mb-1 block">Max per day (USDC)</label>
          <input
            type="number"
            value={maxPerDay}
            onChange={(e) => setMaxPerDay(e.target.value)}
            step="0.001"
            min="0"
            className="input text-xs py-2"
          />
        </div>
      </div>

      <button
        onClick={handleUpdate}
        disabled={updating}
        className="btn-primary w-full text-xs py-2"
      >
        {updating ? "Updating..." : "Update Rules On-Chain"}
      </button>

      {message && (
        <div className={`flex items-center gap-1.5 text-[11px] ${message.includes("fail") ? "text-[var(--color-red)]" : "text-[var(--color-green)]"}`}>
          <CheckCircle2 size={12} />
          {message}
        </div>
      )}
    </div>
  );
}

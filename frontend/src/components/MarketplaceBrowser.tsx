"use client";

import { useState } from "react";
import { registerMarketplaceAgent } from "@/lib/api";
import { Plus, X, CheckCircle2 } from "lucide-react";

/**
 * Stripped-down marketplace component for the sidebar.
 * Just a "+ Register Agent" button that opens a modal form.
 * The agent LIST is now shown in the unified sidebar agent list.
 */
export function MarketplaceBrowser({ onRegistered }: { onRegistered?: () => void }) {
  const [showForm, setShowForm] = useState(false);

  return (
    <div>
      <button
        onClick={() => setShowForm(true)}
        className="btn-primary w-full text-xs py-2 gap-1.5"
      >
        <Plus size={14} />
        Register Agent
      </button>

      {/* Modal overlay */}
      {showForm && (
        <RegisterModal
          onClose={() => setShowForm(false)}
          onSuccess={() => {
            setShowForm(false);
            onRegistered?.();
          }}
        />
      )}
    </div>
  );
}

function RegisterModal({ onClose, onSuccess }: { onClose: () => void; onSuccess: () => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [capabilities, setCapabilities] = useState("");
  const [price, setPrice] = useState("0.0001");
  const [callbackUrl, setCallbackUrl] = useState("");
  const [keywords, setKeywords] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [status, setStatus] = useState<{ type: "ok" | "err"; msg: string } | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setStatus(null);
    try {
      const agent = await registerMarketplaceAgent({
        name: name.trim(),
        description: description.trim(),
        capabilities: capabilities.split(",").map((s) => s.trim()).filter(Boolean),
        price_per_query: parseFloat(price) || 0.0001,
        callback_url: callbackUrl.trim(),
        keywords: keywords.split(",").map((s) => s.trim()).filter(Boolean),
      });
      setStatus({ type: "ok", msg: `Registered! ID: ${agent.agent_id}` });
      setTimeout(onSuccess, 1200);
    } catch (e: unknown) {
      setStatus({ type: "err", msg: e instanceof Error ? e.message : String(e) });
    }
    setSubmitting(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" onClick={onClose} />

      {/* Modal card */}
      <div className="relative card p-6 w-full max-w-md animate-fade-in">
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors"
        >
          <X size={18} />
        </button>

        <h3 className="font-heading text-lg font-semibold mb-1">Register New Agent</h3>
        <p className="text-xs text-[var(--color-text-muted)] mb-5">
          Register an agent running anywhere. It will appear in the marketplace and start earning immediately.
        </p>

        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="text-[11px] font-medium text-[var(--color-text-muted)] mb-1 block">Agent Name *</label>
            <input type="text" value={name} onChange={(e) => setName(e.target.value)} required placeholder="e.g. MyNFT-Agent-v1" className="input text-sm" />
          </div>
          <div>
            <label className="text-[11px] font-medium text-[var(--color-text-muted)] mb-1 block">Description *</label>
            <textarea value={description} onChange={(e) => setDescription(e.target.value)} required placeholder="What this agent does..." rows={2} className="input text-sm resize-none" />
          </div>
          <div>
            <label className="text-[11px] font-medium text-[var(--color-text-muted)] mb-1 block">Capabilities * <span className="text-[var(--color-text-faint)]">(comma-separated)</span></label>
            <input type="text" value={capabilities} onChange={(e) => setCapabilities(e.target.value)} required placeholder="nft_data, nft_analysis" className="input text-sm" />
          </div>
          <div>
            <label className="text-[11px] font-medium text-[var(--color-text-muted)] mb-1 block">Keywords <span className="text-[var(--color-text-faint)]">(optional, comma-separated)</span></label>
            <input type="text" value={keywords} onChange={(e) => setKeywords(e.target.value)} placeholder="nft, floor price, opensea" className="input text-sm" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[11px] font-medium text-[var(--color-text-muted)] mb-1 block">Price (USDC) *</label>
              <input type="text" value={price} onChange={(e) => setPrice(e.target.value)} required className="input text-sm" />
            </div>
            <div>
              <label className="text-[11px] font-medium text-[var(--color-text-muted)] mb-1 block">Callback URL *</label>
              <input type="url" value={callbackUrl} onChange={(e) => setCallbackUrl(e.target.value)} required placeholder="http://..." className="input text-sm" />
            </div>
          </div>

          {status && (
            <div className={`flex items-center gap-1.5 text-xs ${status.type === "ok" ? "text-[var(--color-green)]" : "text-[var(--color-red)]"}`}>
              {status.type === "ok" && <CheckCircle2 size={13} />}
              {status.msg}
            </div>
          )}

          <button type="submit" disabled={submitting} className="btn-primary w-full mt-2">
            {submitting ? "Registering on-chain..." : "Register Agent"}
          </button>
        </form>
      </div>
    </div>
  );
}

"use client";

import type { CategoryStatus, SourceInfo } from "@/lib/api";
import { Activity, CheckCircle2, XCircle, Minus } from "lucide-react";

interface Props {
  status: Record<string, CategoryStatus>;
  degraded?: string[];
}

export function DataHealthBanner({ status, degraded = [] }: Props) {
  if (!status || Object.keys(status).length === 0) return null;

  const categories = Object.entries(status);
  const allGood = degraded.length === 0;

  return (
    <div className={`card p-4 border-l-4 ${allGood ? "border-l-[var(--color-green)]" : "border-l-[var(--color-amber)]"}`}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Activity size={15} className={allGood ? "text-[var(--color-green)]" : "text-[var(--color-amber)]"} />
          <span className="text-xs font-heading font-semibold">
            {allGood ? "All Data Sources Nominal" : `${degraded.length} Source(s) Degraded`}
          </span>
        </div>
        <span className="text-[10px] text-[var(--color-text-muted)]">
          {categories.length} categor{categories.length === 1 ? "y" : "ies"}
        </span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {categories.map(([cat, catStatus]) => {
          const sourceUsed = catStatus.source_used as string | null;
          const unavailable = !sourceUsed || sourceUsed === "unavailable";

          // Collect sub-sources
          const subSources: [string, SourceInfo][] = [];
          for (const [key, val] of Object.entries(catStatus)) {
            if (key === "source_used" || key === "total_tweets" || key === "from_cache") continue;
            if (typeof val === "object" && val !== null) {
              subSources.push([key, val as SourceInfo]);
            }
          }

          return (
            <div key={cat} className="rounded-lg bg-[var(--color-bg-alt)] p-3 border border-[var(--color-border)]">
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-[11px] font-medium capitalize">{cat}</span>
                <span className={`badge text-[9px] ${unavailable ? "badge-red" : "badge-green"}`}>
                  {unavailable ? "Unavailable" : `via ${sourceUsed}`}
                </span>
              </div>
              {subSources.length > 0 && (
                <div className="space-y-0.5">
                  {subSources.map(([name, info]) => {
                    const tried = info.tried !== false;
                    const ok = info.ok === true;
                    return (
                      <div key={name} className="flex items-center justify-between text-[10px]">
                        <div className="flex items-center gap-1.5">
                          {!tried ? (
                            <Minus size={10} className="text-[var(--color-text-faint)]" />
                          ) : ok ? (
                            <CheckCircle2 size={10} className="text-[var(--color-green)]" />
                          ) : (
                            <XCircle size={10} className="text-[var(--color-red)]" />
                          )}
                          <span className="text-[var(--color-text-muted)]">{name}</span>
                        </div>
                        <span className="text-[var(--color-text-muted)] max-w-[55%] text-right break-words">
                          {ok ? `${info.count ?? 0} items` : info.error ? String(info.error) : tried ? "no data" : "skipped"}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

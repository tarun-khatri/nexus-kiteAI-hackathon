"use client";

const STACK = [
  "Groq",
  "Gemini",
  "CoinGecko",
  "DeFiLlama",
  "DEXScreener",
  "GoPlus",
  "Helius",
  "Kite Testnet",
];

export function ZeroCostBand() {
  return (
    <section className="py-12 border-y border-[var(--color-border)] bg-white">
      <div className="container-main">
        <div className="flex flex-col sm:flex-row items-center gap-6 sm:gap-8 justify-between">
          {/* Headline */}
          <div className="text-center sm:text-left shrink-0">
            <div className="font-heading text-xl sm:text-2xl font-extrabold">
              <span className="text-[var(--color-accent)]">$0/month</span>{" "}
              infrastructure.
            </div>
            <p className="text-xs text-[var(--color-text-muted)] mt-1">
              Free-tier LLMs + free-tier data sources + testnet gas.
            </p>
          </div>

          {/* Stack chips */}
          <div className="flex flex-wrap items-center justify-center gap-1.5 sm:gap-2">
            {STACK.map((name, i) => (
              <span
                key={name}
                className="text-[11px] font-medium text-[var(--color-text-secondary)] px-3 py-1.5 rounded-full border border-[var(--color-border)] bg-[var(--color-bg)] whitespace-nowrap"
              >
                {name}
              </span>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

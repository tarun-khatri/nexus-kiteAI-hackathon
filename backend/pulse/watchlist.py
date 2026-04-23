"""
Market Pulse — built-in fallback query pool.

**Not a watchlist anymore.** As of v2, queries are LLM-generated from live
market signals (see backend/pulse/query_generator.py). This file only
exists as the last-resort fallback, used ONLY when:
  1. LLM generation fails (timeout, provider down), AND
  2. capability_registry.example_queries pool is empty (fresh install,
     no marketplace agents registered yet).

In production this path is practically unreachable — the marketplace always
has at least the 3 built-in agents whose example_queries populate the pool.

File kept at this path for backward compatibility with imports.
"""

from __future__ import annotations


BUILT_IN_FALLBACK: list[str] = [
    "BTC sentiment and price trend last 1h",
    "ETH whale activity right now",
    "Top DeFi protocols by TVL change today",
]
"""
Minimal set covering: sentiment/price, whale activity, DeFi health. Just
enough to keep the scheduler fully functional on a completely fresh
install where no agents have registered yet.
"""

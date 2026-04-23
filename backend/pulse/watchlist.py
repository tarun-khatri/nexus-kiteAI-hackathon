"""
Market Pulse — watchlist of autonomous queries.

The scheduler round-robins through this list. Queries are hardcoded by design:
the judging demo is deterministic (same queries, same route paths, same
on-chain proof) and LLM-picked query selection would introduce non-reproducible
behavior and extra compounding cost.

Each entry is a real crypto-intelligence query that routes through 2-5 agents
via the capability registry and produces a real audit trail on Kite testnet.

To add or change a query, edit this file — the scheduler picks up the new list
on next backend restart. No config change needed.
"""

from __future__ import annotations

WATCHLIST: list[str] = [
    "BTC sentiment and price trend last 1h",
    "Top 3 DeFi protocols by TVL change today",
    "ETH whale activity right now",
    "Is SOL bullish or bearish this hour",
    "Latest Solana memecoin launches",
    "Security check on 0xdAC17F958D2ee523a2206206994597C13D831ec7",
]
"""
Rotating list of 6 queries covering: price, sentiment, DeFi, whale activity,
new-token discovery, and security. Each one exercises a different slice of the
capability registry so judges see domain breadth across a handful of runs.
"""


def pick(index: int) -> str:
    """Return the query at `index` (wraps around)."""
    if not WATCHLIST:
        raise RuntimeError("Watchlist is empty — add at least one query.")
    return WATCHLIST[index % len(WATCHLIST)]


def size() -> int:
    return len(WATCHLIST)

"""
Market Pulse — query generator.

Picks the NEXT autonomous query. Three-tier fallback:

  1. LLM-generated from live market signals (BTC/ETH/SOL price delta, fear
     & greed, trending coins, plus the last 5 pulse queries to avoid repeats).
     Primary path — produces genuinely emergent queries that couldn't have
     been pre-written.

  2. capability_registry.example_queries — pool built dynamically from every
     registered agent's self-declared examples. Still dynamic (grows as new
     agents join the marketplace), just deterministic per tick.

  3. Built-in fallback — 3 minimal queries. Reached only if the registry is
     empty (fresh install, no agents registered yet).

The scheduler calls `generate_query()` once per tick. Returns `(query, source)`
where `source` is one of: "llm_generated" | "capability_registry" | "built_in_fallback".
"""

from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone

from backend.llm import llm_router
from backend.marketplace.capability_registry import capability_registry
from backend.pulse.store import load_pulse_runs
from backend.pulse.watchlist import BUILT_IN_FALLBACK


# How long we'll wait for ALL signal calls to return (in total). The LLM
# prompt can still usefully fire with 0-3 signals filled in; we just don't
# want to hold up a tick forever waiting on a slow data source.
SIGNAL_TIMEOUT_SECONDS = 5.0

# How long we'll wait for the LLM to produce a query. Router has its own
# 45s per-provider timeout; ours is tighter because query generation must
# not stall the scheduler.
LLM_TIMEOUT_SECONDS = 10.0

# Bounds for the generated query — guards against LLM hallucinations that
# return a multi-paragraph essay or a 2-word stub.
MIN_QUERY_LEN = 8
MAX_QUERY_LEN = 200


SYSTEM_PROMPT = (
    "You are the query generator for NEXUS Market Pulse, an autonomous "
    "crypto-intelligence scheduler. Every 15 minutes you pick ONE sharp "
    "query for the NEXUS agent economy to investigate. Given live market "
    "signals, produce a single crypto-intelligence question that is "
    "specific, timely, and NOT a repeat of the recent ones. Output ONLY "
    "the query text — no quotes, no markdown, no explanation, no labels. "
    "Maximum 20 words. Single line."
)


async def _gather_signals() -> dict:
    """
    Pull market signals from the existing CoinGecko client. Runs all calls
    in parallel under a single 5s budget — any that time out return empty
    and the prompt just leaves those slots blank.
    """
    # Import lazily to avoid a circular import at package load time.
    import backend.main as main_module

    try:
        coingecko = main_module.data_agent.coingecko
    except Exception:
        return {}

    async def _price(symbol: str):
        try:
            return await coingecko.get_current_price(symbol)
        except Exception:
            return None

    async def _trending():
        try:
            return await coingecko.get_trending()
        except Exception:
            return []

    async def _fng():
        try:
            return await coingecko.get_fear_greed_index()
        except Exception:
            return {}

    try:
        btc, eth, sol, trending, fng = await asyncio.wait_for(
            asyncio.gather(
                _price("BTC"), _price("ETH"), _price("SOL"),
                _trending(), _fng(),
            ),
            timeout=SIGNAL_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        return {}
    except Exception:
        return {}

    return {
        "btc": btc or {},
        "eth": eth or {},
        "sol": sol or {},
        "trending": trending or [],
        "fng": fng or {},
    }


def _fmt_price_line(symbol: str, p: dict) -> str:
    """One-line signal for the prompt. Returns '' if we have no data."""
    if not p:
        return ""
    price = p.get("price") or p.get("current_price")
    change = (
        p.get("change_24h_pct")
        or p.get("price_change_percentage_24h")
        or p.get("percent_change_24h")
    )
    if price is None and change is None:
        return ""
    parts = [f"- {symbol}:"]
    if price is not None:
        try:
            parts.append(f"${float(price):,.2f}")
        except Exception:
            parts.append(str(price))
    if change is not None:
        try:
            parts.append(f"({float(change):+.1f}% 24h)")
        except Exception:
            pass
    return " ".join(parts)


def _build_prompt(signals: dict, recent_queries: list[str]) -> str:
    """Render the USER prompt. Signals missing → slot omitted."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = [f"CURRENT MARKET SIGNALS (as of {ts}):"]

    for sym, key in (("BTC", "btc"), ("ETH", "eth"), ("SOL", "sol")):
        line = _fmt_price_line(sym, signals.get(key) or {})
        if line:
            lines.append(line)

    fng = signals.get("fng") or {}
    fng_val = fng.get("value")
    fng_label = fng.get("label") or fng.get("classification") or ""
    if fng_val is not None:
        lines.append(
            f"- Fear & Greed Index: {fng_val}/100"
            + (f" ({fng_label})" if fng_label else "")
        )

    trending = signals.get("trending") or []
    if trending:
        syms = [str(t.get("symbol") or t.get("name") or "").upper() for t in trending[:7]]
        syms = [s for s in syms if s]
        if syms:
            lines.append(f"- Trending on CoinGecko: {', '.join(syms)}")

    # If we got zero signals, be explicit so the LLM doesn't hallucinate.
    if len(lines) == 1:
        lines.append("- (live market signals temporarily unavailable)")

    if recent_queries:
        lines.append("")
        lines.append("AVOID REPEATING (recent pulse queries):")
        for i, q in enumerate(recent_queries, 1):
            lines.append(f"{i}. {q}")

    lines += [
        "",
        "Pick ONE crypto-intelligence question worth investigating right now.",
        "Examples of useful patterns:",
        "  - Directional sentiment on a specific mover (up or down)",
        "  - Whale activity on a trending asset",
        "  - DeFi protocol TVL change if something spiked",
        "  - Cross-chain or narrative-based questions (L2 flows, memecoin rotation)",
        "  - Security / rug check on a specific trending token",
        "",
        "Query:",
    ]
    return "\n".join(lines)


def _validate_llm_output(raw: str) -> str | None:
    """
    Clean the LLM output and reject anything that doesn't look like a single
    crypto question. Returns the cleaned query or None.
    """
    if not raw:
        return None

    # Strip common LLM decorations
    cleaned = raw.strip()
    cleaned = cleaned.strip("'\"`")       # surrounding quotes
    cleaned = cleaned.removeprefix("Query:").strip()
    cleaned = cleaned.removeprefix("Q:").strip()

    # Multi-line = probably an essay / list → reject
    if "\n" in cleaned:
        return None

    if len(cleaned) < MIN_QUERY_LEN or len(cleaned) > MAX_QUERY_LEN:
        return None

    return cleaned


def _fallback_from_registry() -> str | None:
    """
    Pick a random example query from the live capability registry.
    Filters to providers with non-zero reputation so we don't pull examples
    from a broken/new agent that hasn't proven itself.
    """
    try:
        specs = capability_registry.all_specs()
    except Exception:
        return None

    pool: list[str] = []
    for spec in specs:
        if getattr(spec, "provider_reputation", 0) <= 0:
            continue
        for q in getattr(spec, "example_queries", []) or []:
            q_clean = (q or "").strip()
            if MIN_QUERY_LEN <= len(q_clean) <= MAX_QUERY_LEN:
                pool.append(q_clean)

    if not pool:
        return None
    return random.choice(pool)


def _fallback_builtin() -> str:
    """Last resort. Only hit if registry is empty (fresh install)."""
    return random.choice(BUILT_IN_FALLBACK)


async def generate_query() -> tuple[str, str]:
    """
    Return `(query, source)`. Source is one of:
      - "llm_generated"
      - "capability_registry"
      - "built_in_fallback"

    Guarantees: always returns a non-empty, single-line, crypto-intent-shaped
    string. Never raises — every error path degrades to the next fallback.
    """
    # 1. Gather signals (5s budget)
    signals = await _gather_signals()

    # 2. Fetch recent queries to inject into the "avoid repeating" section
    try:
        recent_runs = await load_pulse_runs(limit=5)
        recent_queries = [r.get("query", "") for r in recent_runs if r.get("query")]
    except Exception:
        recent_queries = []

    # 3. Ask the LLM
    prompt = _build_prompt(signals, recent_queries)
    try:
        raw = await asyncio.wait_for(
            llm_router.generate(prompt, system_prompt=SYSTEM_PROMPT, max_tokens=60),
            timeout=LLM_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        print("[PulseQG] LLM timed out; falling through to registry")
        raw = ""
    except Exception as e:
        print(f"[PulseQG] LLM failed: {type(e).__name__}: {e}; falling through")
        raw = ""

    cleaned = _validate_llm_output(raw)
    if cleaned:
        return (cleaned, "llm_generated")

    # 4. Fallback: capability registry
    from_registry = _fallback_from_registry()
    if from_registry:
        return (from_registry, "capability_registry")

    # 5. Last resort
    return (_fallback_builtin(), "built_in_fallback")

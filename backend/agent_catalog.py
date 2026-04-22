"""
NEXUS - Unified Agent Catalog

THE single source of truth for "all agents in the system." Reads the
AgentRegistry contract on Kite chain for identity + reputation, then
augments with off-chain metadata (capabilities, keywords, callback URLs,
in-process Python references) that aren't stored on-chain.

This module REMOVES the built-in vs marketplace distinction. Every agent
is just an "agent" with one of three source types:
  - "in_process":     Python object we can call directly (the 5 core agents)
  - "http_callback":  External service we invoke via HTTP (e.g., DeFi agent)
  - "on_chain_only":  Registered on-chain by someone else; we can SEE it but
                      can't invoke it because we have no callback / class

Used by:
  - /api/agents endpoint        -> returns the catalog
  - /api/stats endpoint         -> aggregates from catalog
  - DiscoveryEngine             -> selects from catalog
  - Frontend AgentNetworkMap    -> renders the catalog (any N agents)
  - Frontend AgentEarnings/Rep  -> renders the catalog

Caching:
  - Chain reads (slow): 30-second cache
  - SQLite reads (fast): 10-second cache
  - WebSocket events trigger immediate cache invalidation when state changes
"""

import asyncio
import time
from typing import Optional

from backend.blockchain.kite_client import kite_client
from backend.marketplace.registry import marketplace


# Cache TTLs (seconds)
CHAIN_CACHE_TTL = 15        # On-chain reads cached for 15s (fast enough for demo)
TOTALS_CACHE_TTL = 10       # SQLite earnings totals cached for 10s


class AgentCatalog:
    """
    Unified view of all agents (in-process + http-callback + on-chain-only).
    Lazy-cached. Call refresh_from_chain() to invalidate cache explicitly.
    """

    def __init__(self):
        # Map of agent_id (str) -> in-process Python object (BaseAgent subclass).
        # Set once at startup via register_in_process_agents().
        self._in_process: dict[str, object] = {}

        # Cache state
        self._chain_cache: list[dict] = []
        self._chain_cache_at: float = 0
        self._totals_cache: dict[str, dict] = {}
        self._totals_cache_at: float = 0
        self._lock = asyncio.Lock()

    # ---------------------------------------------------------------
    # Setup
    # ---------------------------------------------------------------

    def register_in_process_agents(self, agents: dict[str, object]) -> None:
        """
        Called once at startup with {agent_id: agent_object}.
        These are agents whose handle_request can be called directly in-process.
        """
        self._in_process = dict(agents)

    # ---------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------

    async def get_all(self, force_refresh: bool = False) -> list[dict]:
        """
        Return the unified catalog. One entry per known agent.

        Each entry shape:
            {
                "agent_id": str,
                "passport_id": str | None,
                "name": str,
                "description": str,
                "capabilities": list[str],
                "keywords": list[str],
                "example_queries": list[str],
                "price_per_query": float,
                "reputation_score": int,
                "total_jobs_completed": int,
                "total_earned": float,
                "total_spent": float,
                "wallet_address": str | None,
                "active": bool,
                "status": str,            # "active" | "busy" | "inactive"
                "source_type": str,       # "in_process" | "http_callback" | "on_chain_only"
                "callback_url": str | None,
                "registered_at": int | None,
            }
        """
        async with self._lock:
            now = time.time()
            if force_refresh or (now - self._chain_cache_at) > CHAIN_CACHE_TTL:
                await self._refresh_chain_cache()
            if force_refresh or (now - self._totals_cache_at) > TOTALS_CACHE_TTL:
                await self._refresh_totals_cache()

        # Build merged view: start from chain (authoritative), augment with local.
        chain_by_passport = {a["passport_id"].lower(): a for a in self._chain_cache}
        chain_by_name = {a["name"]: a for a in self._chain_cache}

        out: list[dict] = []
        seen_names: set[str] = set()

        # Pass 1: in-process agents (known Python classes)
        for agent_id, agent in self._in_process.items():
            name = agent.name
            seen_names.add(name)
            chain_data = chain_by_name.get(name) or {}
            entry = self._build_entry(
                agent_id=agent_id,
                source_type="in_process",
                local_agent=agent,
                external_agent=None,
                chain_data=chain_data,
            )
            out.append(entry)

        # Pass 2: external marketplace agents (have callback URLs)
        for ext_id, ext in marketplace.external_agents.items():
            if ext.name in seen_names:
                continue  # in-process takes precedence (shouldn't happen, but defensive)
            seen_names.add(ext.name)
            chain_data = chain_by_name.get(ext.name) or {}
            entry = self._build_entry(
                agent_id=ext_id,
                source_type="http_callback",
                local_agent=None,
                external_agent=ext,
                chain_data=chain_data,
            )
            out.append(entry)

        # Pass 3: on-chain-only agents (registered by someone else; we can't invoke)
        for chain_agent in self._chain_cache:
            if chain_agent["name"] in seen_names:
                continue
            entry = self._build_entry(
                agent_id=f"chain-{chain_agent['passport_id'][:12]}",
                source_type="on_chain_only",
                local_agent=None,
                external_agent=None,
                chain_data=chain_agent,
            )
            out.append(entry)

        return out

    async def get_by_name(self, name: str) -> Optional[dict]:
        all_agents = await self.get_all()
        for a in all_agents:
            if a["name"] == name:
                return a
        return None

    async def get_by_passport(self, passport_id: str) -> Optional[dict]:
        passport_id = passport_id.lower().lstrip("0x")
        all_agents = await self.get_all()
        for a in all_agents:
            pid = (a.get("passport_id") or "").lower().lstrip("0x")
            if pid == passport_id:
                return a
        return None

    async def get_economy_stats(self) -> dict:
        """
        Aggregate stats across ALL agents (in-process + external + on-chain-only).
        """
        agents = await self.get_all()
        total_volume = sum(a["total_earned"] for a in agents)
        total_jobs = sum(a["total_jobs_completed"] for a in agents)
        avg_rep = (
            sum(a["reputation_score"] for a in agents) / len(agents)
            if agents else 0
        )
        # Total transactions = sum of (jobs as payee + as payer counted via spending occurrences).
        # Simpler proxy: total payments observed on-chain.
        try:
            tx_count = await kite_client.get_payment_count()
        except Exception:
            tx_count = 0

        return {
            "economy": {
                "total_agents": len(agents),
                "total_transactions": int(tx_count),
                "total_volume_usdc": round(total_volume, 6),
                "total_jobs_completed": total_jobs,
                "avg_reputation": round(avg_rep, 1),
            },
            "agents": {
                a["agent_id"]: {
                    "earned": a["total_earned"],
                    "spent": a["total_spent"],
                    "jobs": a["total_jobs_completed"],
                    "reputation": a["reputation_score"],
                    "status": a["status"],
                }
                for a in agents
            },
            "governance": {},  # populated by main.py from ReportAgent.governance
        }

    async def refresh_from_chain(self) -> None:
        """Force a chain-cache refresh (called by background sync task)."""
        async with self._lock:
            await self._refresh_chain_cache()
            await self._refresh_totals_cache()

    # ---------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------

    async def _refresh_chain_cache(self) -> None:
        """Read AgentRegistry contract for the full agent list."""
        try:
            agents = await kite_client.get_all_agents_on_chain()
            self._chain_cache = agents
            self._chain_cache_at = time.time()
        except Exception as e:
            print(f"[AgentCatalog] chain cache refresh failed: {e}")

    async def _refresh_totals_cache(self) -> None:
        """
        Compute earnings/spending/jobs per agent name from SQLite transactions.
        SQLite is faster + more accurate than chain reads since some txs
        may be off-chain mode. We fall back to on-chain values if SQLite is empty.
        """
        try:
            from backend.db import load_agent_totals
            new_totals: dict[str, dict] = {}
            # Compute for every known agent name (in-process + external + on-chain).
            names: set[str] = set()
            for a in self._in_process.values():
                names.add(a.name)
            for ext in marketplace.external_agents.values():
                names.add(ext.name)
            for chain_a in self._chain_cache:
                names.add(chain_a["name"])

            for name in names:
                t = await load_agent_totals(name)
                new_totals[name] = t
            self._totals_cache = new_totals
            self._totals_cache_at = time.time()
        except Exception as e:
            print(f"[AgentCatalog] totals cache refresh failed: {e}")

    def _build_entry(
        self,
        agent_id: str,
        source_type: str,
        local_agent: Optional[object],
        external_agent: Optional[object],
        chain_data: dict,
    ) -> dict:
        """
        Merge data from in-process agent + external agent + chain data into
        a single canonical entry. On-chain values are authoritative for
        identity / reputation; off-chain provides invocation metadata.
        """
        # Source priority:
        # name/description/price -> chain > local (chain is authoritative for identity)
        # reputation -> LOCAL PYTHON OBJECT > chain (Python updates instantly on
        #               recordSuccess/recordFailure; chain cache lags by up to 15-30s)
        # jobs -> chain (authoritative counter)
        # capabilities/keywords/example_queries -> local (chain doesn't store them)
        # callback_url -> local
        # status -> in-process Python object (real-time busy/active state)

        if local_agent is not None:
            name = chain_data.get("name") or local_agent.name
            description = chain_data.get("description") or local_agent.description
            price = chain_data.get("price") if chain_data.get("price") is not None else local_agent.price_per_query
            capabilities = list(local_agent.capabilities or [])
            keywords = list(getattr(local_agent, "keywords", []) or [])
            example_queries = list(getattr(local_agent, "example_queries", []) or [])
            wallet = chain_data.get("wallet") or getattr(local_agent, "wallet_address", None)
            passport_id = chain_data.get("passport_id") or getattr(local_agent, "passport_id", None)
            # In-process agents: Python object's reputation is ALWAYS more current
            # than the chain cache because it updates in the same request that calls
            # recordSuccess(). Prefer the live value; fall back to chain on startup
            # (before any queries have been made, the Python default is 50 which may
            # be stale -- but once rehydration runs at startup, it's overwritten with
            # the on-chain value, so both are in sync from that point).
            reputation = local_agent.reputation_score
            jobs = chain_data.get("jobs") if chain_data.get("jobs") is not None else local_agent.total_jobs_completed
            active = chain_data.get("active") if "active" in chain_data else (local_agent.status.value == "active" if hasattr(local_agent.status, "value") else True)
            status = local_agent.status.value if hasattr(local_agent.status, "value") else "active"
            callback_url = None
        elif external_agent is not None:
            name = chain_data.get("name") or external_agent.name
            description = chain_data.get("description") or external_agent.description
            price = chain_data.get("price") if chain_data.get("price") is not None else external_agent.price_per_query
            capabilities = list(external_agent.capabilities or [])
            keywords = list(getattr(external_agent, "keywords", []) or [])
            example_queries = list(getattr(external_agent, "example_queries", []) or [])
            wallet = chain_data.get("wallet")
            passport_id = chain_data.get("passport_id") or getattr(external_agent, "passport_id", None)
            # Prefer the LOCAL in-memory reputation (updated synchronously on
            # every successful invocation) over the chain cache (15-60s stale).
            # This matches what we do for built-in agents and keeps the UI
            # responsive without waiting for chain cache refresh.
            reputation = external_agent.reputation_score
            jobs = max(external_agent.total_jobs, int(chain_data.get("jobs") or 0))
            active = chain_data.get("active") if "active" in chain_data else external_agent.active
            status = "active" if active else "inactive"
            callback_url = external_agent.callback_url
        else:
            # On-chain-only: we know it exists but can't invoke it.
            name = chain_data.get("name", "unknown")
            description = chain_data.get("description", "")
            price = chain_data.get("price", 0)
            capabilities = []
            keywords = []
            example_queries = []
            wallet = chain_data.get("wallet")
            passport_id = chain_data.get("passport_id")
            reputation = chain_data.get("reputation", 50)
            jobs = chain_data.get("jobs", 0)
            active = chain_data.get("active", True)
            status = "active" if active else "inactive"
            callback_url = None

        # Pull SQLite-computed totals (more granular than chain auto-tracking).
        totals = self._totals_cache.get(name) or {"total_earned": 0.0, "total_spent": 0.0, "total_jobs": 0}
        total_earned = totals["total_earned"]
        total_spent = totals["total_spent"]
        # Prefer chain-tracked jobs if present; fall back to SQLite.
        if not jobs and totals["total_jobs"]:
            jobs = totals["total_jobs"]

        return {
            "agent_id": agent_id,
            "passport_id": passport_id,
            "name": name,
            "description": description,
            "capabilities": capabilities,
            "keywords": keywords,
            "example_queries": example_queries,
            "price_per_query": price,
            "reputation_score": reputation,
            "total_jobs_completed": jobs,
            "total_earned": total_earned,
            "total_spent": total_spent,
            "wallet_address": wallet,
            "active": active,
            "status": status,
            "source_type": source_type,
            "callback_url": callback_url,
            "registered_at": chain_data.get("registered_at"),
        }


# Module-level singleton
agent_catalog = AgentCatalog()

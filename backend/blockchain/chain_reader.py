"""
NEXUS - Chain Reader

A thin async facade over the four deployed contracts that turns on-chain view
functions into the authoritative source for:
  - Reputation records (score, total/success/fail counts)
  - Payment totals (earned, spent, payment_count)
  - Agent registry sweeps (everyone on-chain, not just those we know locally)
  - Recent payments (for the whale-as-agent feed)

Everything is keyed on passport_id (bytes32) — the one identifier that has
meaning on-chain. Works for any registered agent, current or future.

Caching: per-call parallelism via asyncio.gather + a 5-second result cache
(tunable). View-function reads are free, but RPC round-trips add up; the
cache keeps routine dashboard polls snappy.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional

from backend.blockchain.kite_client import kite_client


# ---------- Data shapes ----------

@dataclass
class ReputationRecord:
    passport_id: str          # hex string (no 0x)
    score: int
    total_jobs: int
    successful_jobs: int
    failed_jobs: int

    @property
    def success_rate(self) -> float:
        return (self.successful_jobs / self.total_jobs) if self.total_jobs else 0.0


@dataclass
class PaymentTotals:
    passport_id: str
    total_earned_usdc: float
    total_spent_usdc: float


@dataclass
class OnchainAgentRecord:
    passport_id: str
    wallet: str
    name: str
    description: str
    price_usdc: float
    reputation: int
    active: bool
    jobs: int
    registered_at: int


@dataclass
class OnchainPayment:
    index: int
    from_passport: str
    to_passport: str
    amount_usdc: float
    purpose: str
    mandate_id: str
    timestamp: int


@dataclass
class EconomySnapshot:
    payment_count: int
    total_volume_usdc: float
    total_agents: int
    top_earners: list[dict]      # [{agent, earned, jobs}]
    chain_id: int
    source: str = "kite-onchain"


# ---------- Chain reader ----------

class ChainReader:
    """
    Read-only facade over kite_client. Every method is safe to call on every
    request (view calls cost no gas); the cache just reduces RPC chatter.
    """

    def __init__(self, ttl_seconds: float = 5.0):
        self.ttl = ttl_seconds
        self._cache: dict[str, tuple[float, object]] = {}

    # ----- Cache helpers -----

    def _get_cached(self, key: str):
        entry = self._cache.get(key)
        if entry and (time.time() - entry[0]) < self.ttl:
            return entry[1]
        return None

    def _set_cached(self, key: str, value):
        self._cache[key] = (time.time(), value)

    def invalidate(self, prefix: Optional[str] = None):
        if prefix is None:
            self._cache.clear()
            return
        for k in list(self._cache.keys()):
            if k.startswith(prefix):
                del self._cache[k]

    # ----- Reputation -----

    async def get_reputation_record(
        self, passport_id: bytes | str,
    ) -> Optional[ReputationRecord]:
        """One agent's full reputation record. Returns None if chain unavailable."""
        if not kite_client.reputation_contract:
            return None

        pid_bytes = self._to_bytes(passport_id)
        pid_hex = pid_bytes.hex()

        cached = self._get_cached(f"rep|{pid_hex}")
        if cached is not None:
            return cached

        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                lambda: kite_client.reputation_contract.functions.getFullRecord(pid_bytes).call(),
            )
            score, total, success, fail = result
            rec = ReputationRecord(
                passport_id=pid_hex,
                score=int(score),
                total_jobs=int(total),
                successful_jobs=int(success),
                failed_jobs=int(fail),
            )
            self._set_cached(f"rep|{pid_hex}", rec)
            return rec
        except Exception as e:
            print(f"[ChainReader] getFullRecord({pid_hex[:12]}...) failed: {e}")
            return None

    async def get_bulk_reputation(
        self, passport_ids: list[bytes | str],
    ) -> dict[str, ReputationRecord]:
        """Fetch reputation for many agents in parallel."""
        if not passport_ids:
            return {}
        results = await asyncio.gather(
            *[self.get_reputation_record(p) for p in passport_ids],
            return_exceptions=False,
        )
        out: dict[str, ReputationRecord] = {}
        for rec in results:
            if rec is not None:
                out[rec.passport_id] = rec
        return out

    # ----- Payment totals -----

    async def get_payment_totals(
        self, passport_id: bytes | str,
    ) -> PaymentTotals:
        pid_bytes = self._to_bytes(passport_id)
        pid_hex = pid_bytes.hex()

        cached = self._get_cached(f"pay|{pid_hex}")
        if cached is not None:
            return cached

        if not kite_client.payment_contract:
            return PaymentTotals(pid_hex, 0.0, 0.0)

        try:
            loop = asyncio.get_running_loop()
            earned_raw, spent_raw = await asyncio.gather(
                loop.run_in_executor(None, lambda: kite_client.payment_contract.functions.getTotalEarned(pid_bytes).call()),
                loop.run_in_executor(None, lambda: kite_client.payment_contract.functions.getTotalSpent(pid_bytes).call()),
            )
            totals = PaymentTotals(
                passport_id=pid_hex,
                total_earned_usdc=float(earned_raw) / 1_000_000,
                total_spent_usdc=float(spent_raw) / 1_000_000,
            )
            self._set_cached(f"pay|{pid_hex}", totals)
            return totals
        except Exception as e:
            print(f"[ChainReader] getTotalEarned/Spent({pid_hex[:12]}...) failed: {e}")
            return PaymentTotals(pid_hex, 0.0, 0.0)

    async def get_bulk_payment_totals(
        self, passport_ids: list[bytes | str],
    ) -> dict[str, PaymentTotals]:
        if not passport_ids:
            return {}
        results = await asyncio.gather(*[self.get_payment_totals(p) for p in passport_ids])
        return {t.passport_id: t for t in results}

    async def get_payment_count(self) -> int:
        cached = self._get_cached("paycount")
        if cached is not None:
            return cached
        count = await kite_client.get_payment_count()
        self._set_cached("paycount", count)
        return count

    # ----- Agent registry sweep -----

    async def get_all_registered_agents(self) -> list[OnchainAgentRecord]:
        cached = self._get_cached("allagents")
        if cached is not None:
            return cached

        raw = await kite_client.get_all_agents_on_chain()
        out = [
            OnchainAgentRecord(
                passport_id=r["passport_id"],
                wallet=r.get("wallet", ""),
                name=r.get("name", ""),
                description=r.get("description", ""),
                price_usdc=float(r.get("price", 0.0)),
                reputation=int(r.get("reputation", 0)),
                active=bool(r.get("active", True)),
                jobs=int(r.get("jobs", 0)),
                registered_at=int(r.get("registered_at", 0)),
            )
            for r in (raw or [])
        ]
        self._set_cached("allagents", out)
        return out

    # ----- Recent payments -----

    async def get_recent_payments(self, limit: int = 200) -> list[OnchainPayment]:
        cached = self._get_cached(f"recent|{limit}")
        if cached is not None:
            return cached

        raw = await kite_client.get_all_payments_from_chain(limit=limit)
        out = [
            OnchainPayment(
                index=int(r.get("index", 0)),
                from_passport=str(r.get("from_passport", "")),
                to_passport=str(r.get("to_passport", "")),
                amount_usdc=float(r.get("amount", 0.0)),
                purpose=str(r.get("purpose", "")),
                mandate_id=str(r.get("mandate_id", "")),
                timestamp=int(r.get("timestamp", 0)),
            )
            for r in (raw or [])
        ]
        self._set_cached(f"recent|{limit}", out)
        return out

    # ----- Aggregated economy snapshot -----

    async def get_economy_snapshot_cached(
        self,
        passport_to_name: Optional[dict[str, str]] = None,
        max_age_seconds: float = 20.0,
    ) -> Optional[EconomySnapshot]:
        """
        Return the most recent cached EconomySnapshot if it's fresh enough,
        else None. Non-blocking — never waits on the RPC. Designed for the
        hot polling path (/api/stats, /api/reputation).
        """
        cached = self._cache.get("econ_snapshot")
        if cached and (time.time() - cached[0]) < max_age_seconds:
            return cached[1]
        return None

    async def refresh_economy_snapshot(
        self,
        passport_to_name: Optional[dict[str, str]] = None,
    ) -> EconomySnapshot:
        """Force-refresh the economy snapshot and store it. Use from a background task."""
        snap = await self.get_economy_snapshot(passport_to_name)
        self._cache["econ_snapshot"] = (time.time(), snap)
        return snap

    async def get_economy_snapshot(
        self,
        passport_to_name: Optional[dict[str, str]] = None,
    ) -> EconomySnapshot:
        """Reputation-weighted top earners + volume + counts. All on-chain."""
        agents, payment_count = await asyncio.gather(
            self.get_all_registered_agents(),
            self.get_payment_count(),
        )

        totals = await self.get_bulk_payment_totals(
            [a.passport_id for a in agents]
        )

        total_volume = sum(t.total_earned_usdc for t in totals.values())

        # Top 5 by earnings
        enriched = []
        for a in agents:
            t = totals.get(a.passport_id)
            if not t:
                continue
            enriched.append({
                "agent_name": a.name or (passport_to_name or {}).get(a.passport_id, a.passport_id[:16]),
                "passport_id": a.passport_id,
                "earned_usdc": t.total_earned_usdc,
                "spent_usdc": t.total_spent_usdc,
                "jobs": a.jobs,
                "reputation": a.reputation,
            })
        enriched.sort(key=lambda x: x["earned_usdc"], reverse=True)

        chain_id = 0
        try:
            if kite_client.w3 and kite_client.connected:
                chain_id = kite_client.w3.eth.chain_id
        except Exception:
            chain_id = 0

        return EconomySnapshot(
            payment_count=payment_count,
            total_volume_usdc=round(total_volume, 6),
            total_agents=len(agents),
            top_earners=enriched[:5],
            chain_id=chain_id,
        )

    # ----- Utilities -----

    @staticmethod
    def _to_bytes(passport_id: bytes | str) -> bytes:
        if isinstance(passport_id, (bytes, bytearray)):
            return bytes(passport_id)
        s = str(passport_id)
        if s.startswith("0x"):
            s = s[2:]
        # Left-pad to 32 bytes (64 hex chars) just in case.
        s = s.rjust(64, "0")
        try:
            return bytes.fromhex(s)
        except ValueError:
            return b"\x00" * 32


# Global singleton
chain_reader = ChainReader()

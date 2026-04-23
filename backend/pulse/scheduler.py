"""
Market Pulse scheduler — the autonomous trigger loop.

Runs as a background asyncio task started by the FastAPI lifespan. Every
`settings.pulse_interval_seconds` it generates a query via the LLM
(backend/pulse/query_generator.py) and fires `report_agent.handle_request()` —
the same entry point a human query hits. Each run produces real mandates,
real x402 payments, real on-chain audit trails, real reputation updates.
The only difference is: no one typed the query.

Failures are persisted (status="error") and logged; they never crash the loop.
`asyncio.CancelledError` propagates so lifespan shutdown is clean.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from backend.config import settings
from backend.models.events import NexusEvent, EventType
from backend.websocket.manager import ws_manager
from backend.pulse.query_generator import generate_query
from backend.pulse.store import save_pulse_run


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PulseScheduler:
    """
    Singleton scheduler. Instantiated at module load; started via run() from
    lifespan startup and cancelled from lifespan shutdown.
    """

    def __init__(self) -> None:
        self._run_count: int = 0
        self._last_run_at: Optional[datetime] = None
        self._next_run_at: Optional[datetime] = None
        self._last_query_source: Optional[str] = None
        self._running: bool = False

    # ---------------------------------------------------------- status

    def status(self) -> dict:
        """Current scheduler state for GET /api/pulse/status."""
        now = datetime.now(timezone.utc)
        seconds_since = (
            (now - self._last_run_at).total_seconds()
            if self._last_run_at is not None else None
        )
        return {
            "enabled": settings.pulse_enabled,
            "running": self._running,
            "interval_seconds": settings.pulse_interval_seconds,
            "initial_delay_seconds": settings.pulse_initial_delay_seconds,
            "run_count": self._run_count,
            "last_run_at": self._last_run_at.isoformat() if self._last_run_at else None,
            "next_run_at": self._next_run_at.isoformat() if self._next_run_at else None,
            "seconds_since_last_run": (
                round(seconds_since) if seconds_since is not None else None
            ),
            "last_query_source": self._last_query_source,
        }

    # ---------------------------------------------------------- main loop

    async def run(self) -> None:
        """
        Entry point for the asyncio task. Wait the initial-delay grace period
        (so startup rehydrate + cache warm + first chain sync finish), then
        loop forever: generate query → execute → persist → broadcast → sleep.
        """
        self._running = True
        try:
            if settings.pulse_initial_delay_seconds > 0:
                # Advertise the first run time up front so /api/pulse/status
                # during the grace period shows "next_run_at = T+delay".
                self._next_run_at = datetime.now(timezone.utc) + timedelta(
                    seconds=settings.pulse_initial_delay_seconds
                )
                await asyncio.sleep(settings.pulse_initial_delay_seconds)

            while True:
                # Generate the next query from live signals. Falls back
                # automatically through the chain defined in query_generator.
                try:
                    query, query_source = await generate_query()
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    # generate_query() is supposed to never raise, but
                    # defensively handle it anyway. Use a minimal fallback
                    # and note the source as "fallback_error" so observability
                    # captures that something went wrong upstream.
                    print(f"[Pulse] query_generator raised: {type(e).__name__}: {e}")
                    from backend.pulse.watchlist import BUILT_IN_FALLBACK
                    import random
                    query = random.choice(BUILT_IN_FALLBACK)
                    query_source = "built_in_fallback"

                try:
                    await self.run_once(query, trigger_source="scheduled",
                                        query_source=query_source)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    # A single bad run must never kill the scheduler.
                    print(f"[Pulse] Unexpected loop error: {type(e).__name__}: {e}")

                self._next_run_at = datetime.now(timezone.utc) + timedelta(
                    seconds=settings.pulse_interval_seconds
                )
                await asyncio.sleep(settings.pulse_interval_seconds)
        except asyncio.CancelledError:
            print("[Pulse] Scheduler cancelled; exiting loop cleanly.")
            raise
        finally:
            self._running = False

    # ---------------------------------------------------------- single run

    async def run_once(
        self,
        query: str,
        trigger_source: str = "manual",
        query_source: str = "unknown",
    ) -> dict:
        """
        Execute one run end-to-end. Broadcasts PULSE_RUN_STARTED, drives the
        orchestrator via report_agent, persists the row, broadcasts either
        PULSE_RUN_COMPLETED or PULSE_RUN_FAILED.

        `query_source` tags HOW the query was picked: "llm_generated",
        "capability_registry", "built_in_fallback", or "manual" when the user
        hits the trigger endpoint and bypasses the generator.
        """
        import backend.main as main_module  # lazy — avoid circular import

        run_id = f"pulse-{uuid.uuid4().hex[:12]}"
        started_at = datetime.now(timezone.utc)
        t0 = time.time()

        # --- Broadcast START so the dashboard feed shows it ---
        await ws_manager.broadcast(NexusEvent(
            event_type=EventType.PULSE_RUN_STARTED,
            agent_id="MarketPulse",
            data={
                "run_id": run_id,
                "query": query,
                "trigger": trigger_source,
                "query_source": query_source,
            },
            message=f"Market Pulse ({query_source}): '{query}'",
        ))

        try:
            # Drive through the SAME path /api/query uses. No special-casing.
            # This is where x402 payments, mandate signing, audit trail writes
            # actually fire — identical to a human query.
            report = await main_module.report_agent.handle_request({
                "query": query,
                "enrichments": "auto",
            })
        except asyncio.CancelledError:
            raise
        except Exception as e:
            err_msg = f"{type(e).__name__}: {e}"
            print(f"[Pulse] Run {run_id} failed during orchestration: {err_msg}")
            completed_at = datetime.now(timezone.utc)
            failure = {
                "run_id": run_id,
                "query": query,
                "trigger_source": trigger_source,
                "query_source": query_source,
                "status": "error",
                "agents_involved": 0,
                "total_cost_usdc": 0.0,
                "total_time_ms": int((time.time() - t0) * 1000),
                "error_message": err_msg,
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
                # Empty payment list for failed runs
                "payment_tx_hashes_json": json.dumps([]),
            }
            await save_pulse_run(failure)
            await ws_manager.broadcast(NexusEvent(
                event_type=EventType.PULSE_RUN_FAILED,
                agent_id="MarketPulse",
                data={
                    "run_id": run_id,
                    "query": query,
                    "query_source": query_source,
                    "error": err_msg,
                },
                message=f"Market Pulse run failed: {err_msg}",
            ))
            self._run_count += 1
            self._last_run_at = completed_at
            self._last_query_source = query_source
            return failure

        # --- Happy path: extract the proof bits we surface on /pulse ---
        completed_at = datetime.now(timezone.utc)
        audit_trail = (report.get("audit_trail") or {})
        economy = (report.get("economy_stats") or {})
        vi = (report.get("verified_intent") or {})

        audit_tx_hash = audit_trail.get("on_chain_tx_hash")

        # v2: persist the FULL transaction detail, not just hashes. This is
        # what lets /pulse drill-down show "Agent A paid Agent B $0.0001 for
        # data_fetch, tx=0x..." instead of just a bare hash list.
        raw_transactions = economy.get("transactions") or []
        payments_detail: list[dict] = []
        for t in raw_transactions:
            tx_hash = t.get("tx_hash")
            if not tx_hash:
                continue  # skip unsettled or blocked payments
            payments_detail.append({
                "from_agent": t.get("from") or "",
                "to_agent": t.get("to") or "",
                "amount": float(t.get("amount") or 0.0),
                "purpose": t.get("purpose") or "",
                "tx_hash": tx_hash,
                "status": t.get("status") or "confirmed",
            })

        run_dict = {
            "run_id": run_id,
            "query": query,
            "trigger_source": trigger_source,
            "query_source": query_source,
            "report_id": report.get("report_id"),
            "summary": (report.get("summary") or "")[:500],
            "status": report.get("status") or "ok",
            "agents_involved": int(economy.get("agents_involved") or 0),
            "total_cost_usdc": float(economy.get("total_cost_usdc") or 0.0),
            "total_time_ms": int(economy.get("total_time_ms") or 0),
            "audit_tx_hash": audit_tx_hash,
            "payment_tx_hashes_json": json.dumps(payments_detail),
            "mandate_id": vi.get("mandate_id"),
            "error_message": None,
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
        }

        await save_pulse_run(run_dict)

        # Pretty log for ops visibility
        tx_hint = audit_tx_hash[:16] + "…" if audit_tx_hash else "(no chain tx)"
        print(
            f"[Pulse] Run #{self._run_count + 1} ({query_source}): "
            f"'{query}' — "
            f"{run_dict['agents_involved']} agents, "
            f"${run_dict['total_cost_usdc']:.4f}, "
            f"{run_dict['total_time_ms']}ms, tx={tx_hint}"
        )

        await ws_manager.broadcast(NexusEvent(
            event_type=EventType.PULSE_RUN_COMPLETED,
            agent_id="MarketPulse",
            data={
                "run_id": run_id,
                "query": query,
                "query_source": query_source,
                "report_id": run_dict["report_id"],
                "agents": run_dict["agents_involved"],
                "cost": run_dict["total_cost_usdc"],
                "audit_tx_hash": audit_tx_hash,
                "payments_count": len(payments_detail),
            },
            message=(
                f"Market Pulse ({query_source}): {query} — "
                f"{run_dict['agents_involved']} agents, "
                f"${run_dict['total_cost_usdc']:.4f}"
            ),
        ))

        self._run_count += 1
        self._last_run_at = completed_at
        self._last_query_source = query_source
        return run_dict


# Module-level singleton used by main.py lifespan + API endpoints.
pulse_scheduler = PulseScheduler()

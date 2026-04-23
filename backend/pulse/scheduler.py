"""
Market Pulse scheduler — the autonomous trigger loop.

Runs as a background asyncio task started by the FastAPI lifespan. Every
`settings.pulse_interval_seconds` it rotates through WATCHLIST and fires
`report_agent.handle_request()` — the same entry point a human query hits.
Each run produces real mandates, real x402 payments, real on-chain audit
trails, real reputation updates. The only difference is no one typed a query.

Failures are persisted (status="error") and logged; they never crash the loop.
`asyncio.CancelledError` propagates so lifespan shutdown is clean.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from backend.config import settings
from backend.models.events import NexusEvent, EventType
from backend.websocket.manager import ws_manager
from backend.pulse.watchlist import pick, size as watchlist_size
from backend.pulse.store import save_pulse_run


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PulseScheduler:
    """
    Singleton scheduler. Instantiated at module load; started via run() from
    lifespan startup and cancelled from lifespan shutdown.
    """

    def __init__(self) -> None:
        self._index: int = 0
        self._run_count: int = 0
        self._last_run_at: Optional[datetime] = None
        self._next_run_at: Optional[datetime] = None
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
            "watchlist_size": watchlist_size(),
            "watchlist_next_index": self._index % watchlist_size(),
            "run_count": self._run_count,
            "last_run_at": self._last_run_at.isoformat() if self._last_run_at else None,
            "next_run_at": self._next_run_at.isoformat() if self._next_run_at else None,
            "seconds_since_last_run": (
                round(seconds_since) if seconds_since is not None else None
            ),
        }

    # ---------------------------------------------------------- main loop

    async def run(self) -> None:
        """
        Entry point for the asyncio task. Wait the initial-delay grace period
        (so startup rehydrate + cache warm + first chain sync finish), then
        loop forever: pick → execute → persist → broadcast → sleep.
        """
        self._running = True
        try:
            if settings.pulse_initial_delay_seconds > 0:
                # Advertise the first run time up front so /api/pulse/status
                # during the grace period shows "next_run_at = T+delay".
                from datetime import timedelta as _td
                self._next_run_at = datetime.now(timezone.utc) + _td(
                    seconds=settings.pulse_initial_delay_seconds
                )
                await asyncio.sleep(settings.pulse_initial_delay_seconds)

            while True:
                query = pick(self._index)
                self._index += 1

                try:
                    await self.run_once(query, trigger_source="scheduled")
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    # A single bad run must never kill the scheduler.
                    print(f"[Pulse] Unexpected loop error: {type(e).__name__}: {e}")

                # Advertise next run
                from datetime import timedelta as _td
                self._next_run_at = datetime.now(timezone.utc) + _td(
                    seconds=settings.pulse_interval_seconds
                )
                await asyncio.sleep(settings.pulse_interval_seconds)
        except asyncio.CancelledError:
            print("[Pulse] Scheduler cancelled; exiting loop cleanly.")
            raise
        finally:
            self._running = False

    # ---------------------------------------------------------- single run

    async def run_once(self, query: str, trigger_source: str = "manual") -> dict:
        """
        Execute one run end-to-end. Broadcasts PULSE_RUN_STARTED, drives the
        orchestrator via report_agent, persists the row, broadcasts either
        PULSE_RUN_COMPLETED or PULSE_RUN_FAILED.

        Returns the persisted run dict (or the failure dict).
        """
        # Lazy import to avoid circular startup dependency.
        from backend.agents.report_agent import ReportAgent  # noqa: F401  (type only)
        import backend.main as main_module  # to grab the singleton report_agent

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
            },
            message=f"Market Pulse: autonomous run — '{query}'",
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
                "status": "error",
                "agents_involved": 0,
                "total_cost_usdc": 0.0,
                "total_time_ms": int((time.time() - t0) * 1000),
                "error_message": err_msg,
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
            }
            await save_pulse_run(failure)
            await ws_manager.broadcast(NexusEvent(
                event_type=EventType.PULSE_RUN_FAILED,
                agent_id="MarketPulse",
                data={"run_id": run_id, "query": query, "error": err_msg},
                message=f"Market Pulse run failed: {err_msg}",
            ))
            self._run_count += 1
            self._last_run_at = completed_at
            return failure

        # --- Happy path: extract the proof bits we surface on /pulse ---
        completed_at = datetime.now(timezone.utc)
        audit_trail = (report.get("audit_trail") or {})
        economy = (report.get("economy_stats") or {})
        vi = (report.get("verified_intent") or {})

        audit_tx_hash = audit_trail.get("on_chain_tx_hash")
        payment_tx_hashes = [
            t.get("tx_hash") for t in (economy.get("transactions") or [])
            if t.get("tx_hash")
        ]

        run_dict = {
            "run_id": run_id,
            "query": query,
            "trigger_source": trigger_source,
            "report_id": report.get("report_id"),
            "summary": (report.get("summary") or "")[:500],
            "status": report.get("status") or "ok",
            "agents_involved": int(economy.get("agents_involved") or 0),
            "total_cost_usdc": float(economy.get("total_cost_usdc") or 0.0),
            "total_time_ms": int(economy.get("total_time_ms") or 0),
            "audit_tx_hash": audit_tx_hash,
            "payment_tx_hashes_json": json.dumps(payment_tx_hashes),
            "mandate_id": vi.get("mandate_id"),
            "error_message": None,
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
        }

        await save_pulse_run(run_dict)

        # Pretty log for ops visibility
        tx_hint = audit_tx_hash[:16] + "…" if audit_tx_hash else "(no chain tx)"
        print(
            f"[Pulse] Run #{self._run_count + 1} completed: '{query}' — "
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
                "report_id": run_dict["report_id"],
                "agents": run_dict["agents_involved"],
                "cost": run_dict["total_cost_usdc"],
                "audit_tx_hash": audit_tx_hash,
                "payment_tx_hashes": payment_tx_hashes,
            },
            message=(
                f"Market Pulse: {query} — "
                f"{run_dict['agents_involved']} agents, "
                f"${run_dict['total_cost_usdc']:.4f}"
            ),
        ))

        self._run_count += 1
        self._last_run_at = completed_at
        return run_dict


# Module-level singleton used by main.py lifespan + API endpoints.
pulse_scheduler = PulseScheduler()

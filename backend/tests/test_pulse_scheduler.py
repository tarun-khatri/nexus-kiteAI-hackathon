"""
Tests for the Market Pulse autonomous-trigger scheduler.

These tests exercise the pulse pipeline WITHOUT hitting the chain, the LLM,
or the real orchestrator — `report_agent.handle_request` is mocked and
`ws_manager.broadcast` is patched to a capture list. DB writes go to a
temporary SQLite file so test state is isolated per run.
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio


# ============================================================
# Fixtures
# ============================================================

@pytest_asyncio.fixture
async def tmp_db(monkeypatch):
    """
    Point db.DB_PATH at a fresh tempfile, initialize the schema, yield,
    then remove the file. Each test gets a clean `pulse_runs` table.
    """
    fd, path = tempfile.mkstemp(prefix="nexus-pulse-test-", suffix=".db")
    os.close(fd)

    # Patch the module-level DB_PATH everywhere it's read.
    import backend.db as db_mod
    monkeypatch.setattr(db_mod, "DB_PATH", path)
    # store.py re-imports at call time, so patching db_mod is enough;
    # but be defensive.
    import backend.pulse.store as store_mod
    monkeypatch.setattr(store_mod, "DB_PATH", path)

    await db_mod.init_db()

    yield path

    try:
        os.remove(path)
    except OSError:
        pass


@pytest.fixture
def fresh_scheduler():
    """
    Return a new PulseScheduler instance so test state (index, counters)
    is clean across tests.
    """
    from backend.pulse.scheduler import PulseScheduler
    return PulseScheduler()


# A realistic report dict matching report_agent.handle_request return shape.
FAKE_REPORT: dict[str, Any] = {
    "report_id": "rpt-test-12345",
    "query": "BTC sentiment and price trend last 1h",
    "status": "ok",
    "summary": "BTC sentiment is moderately bullish with 58% positive signal.",
    "classification": {"status": "routed"},
    "sections": {},
    "output_fields": {},
    "economy_stats": {
        "total_cost_usdc": 0.0003,
        "total_time_ms": 12345,
        "agents_involved": 3,
        "transactions": [
            {"from": "A", "to": "B", "amount": 0.0001, "tx_hash": "0xaa" + "11" * 31},
            {"from": "A", "to": "C", "amount": 0.0002, "tx_hash": "0xbb" + "22" * 31},
        ],
    },
    "verified_intent": {"mandate_id": "mnd-test-xyz"},
    "audit_trail": {
        "trail_id": "trail-test",
        "on_chain_tx_hash": "0xcc" + "33" * 31,
        "explorer_url": "https://testnet.kitescan.ai/tx/0xcc" + "33" * 31,
    },
}


# ============================================================
# 1. Watchlist rotation
# ============================================================

def test_watchlist_rotation():
    """Scheduler's index cursor must wrap around the watchlist list cleanly."""
    from backend.pulse.watchlist import WATCHLIST, pick, size

    n = size()
    assert n >= 1
    assert len(WATCHLIST) == n

    # First N picks return each query once in order
    first_round = [pick(i) for i in range(n)]
    assert first_round == list(WATCHLIST)

    # Index n wraps to the 0th entry
    assert pick(n) == WATCHLIST[0]
    assert pick(n + 1) == WATCHLIST[1]
    # A huge index still works
    assert pick(10 * n + 3) == WATCHLIST[3 % n]


# ============================================================
# 2. run_once persists a row with expected fields
# ============================================================

@pytest.mark.asyncio
async def test_run_once_persists_row(tmp_db, fresh_scheduler):
    """A successful run_once should write a complete row to pulse_runs."""
    from backend.pulse.store import load_pulse_runs
    import backend.main as main_module

    # Stub out the real report_agent singleton — we don't want to touch
    # LLMs, chain, or the orchestrator in a unit test.
    with patch.object(
        main_module,
        "report_agent",
        new=type("X", (), {"handle_request": AsyncMock(return_value=FAKE_REPORT)})(),
    ):
        # Silence ws_manager so the test doesn't need a WebSocket client
        with patch(
            "backend.pulse.scheduler.ws_manager.broadcast", new=AsyncMock()
        ):
            run = await fresh_scheduler.run_once(
                "BTC sentiment and price trend last 1h",
                trigger_source="scheduled",
            )

    assert run["status"] == "ok"
    assert run["agents_involved"] == 3
    assert run["total_cost_usdc"] == pytest.approx(0.0003)
    assert run["audit_tx_hash"] == "0xcc" + "33" * 31
    assert run["mandate_id"] == "mnd-test-xyz"
    assert run["trigger_source"] == "scheduled"
    assert run["run_id"].startswith("pulse-")

    # And it should be readable back from the DB.
    rows = await load_pulse_runs(limit=10)
    assert len(rows) == 1
    row = rows[0]
    assert row["run_id"] == run["run_id"]
    assert row["query"] == "BTC sentiment and price trend last 1h"
    assert row["agents_involved"] == 3
    assert row["audit_tx_hash"] == "0xcc" + "33" * 31
    # payment_tx_hashes is a list of strings after JSON decode in load
    assert isinstance(row["payment_tx_hashes"], list)
    assert len(row["payment_tx_hashes"]) == 2


# ============================================================
# 3. Broadcast events: STARTED + COMPLETED (success path)
# ============================================================

@pytest.mark.asyncio
async def test_run_once_emits_started_and_completed(tmp_db, fresh_scheduler):
    """Happy path must emit PULSE_RUN_STARTED then PULSE_RUN_COMPLETED."""
    import backend.main as main_module
    from backend.models.events import EventType

    captured_events: list = []

    async def _capture(event):
        captured_events.append(event)

    with patch.object(
        main_module,
        "report_agent",
        new=type("X", (), {"handle_request": AsyncMock(return_value=FAKE_REPORT)})(),
    ):
        with patch(
            "backend.pulse.scheduler.ws_manager.broadcast",
            new=AsyncMock(side_effect=_capture),
        ):
            await fresh_scheduler.run_once("test q", trigger_source="manual")

    event_types = [e.event_type for e in captured_events]
    assert EventType.PULSE_RUN_STARTED in event_types
    assert EventType.PULSE_RUN_COMPLETED in event_types
    # Start must precede complete
    assert event_types.index(EventType.PULSE_RUN_STARTED) < event_types.index(
        EventType.PULSE_RUN_COMPLETED
    )


# ============================================================
# 4. Failure handling — persists error row + emits FAILED, doesn't crash
# ============================================================

@pytest.mark.asyncio
async def test_run_once_handles_orchestrator_failure(tmp_db, fresh_scheduler):
    """If handle_request raises, we must persist status=error and emit FAILED."""
    from backend.pulse.store import load_pulse_runs
    from backend.models.events import EventType
    import backend.main as main_module

    captured_events: list = []

    async def _capture(event):
        captured_events.append(event)

    class BrokenReportAgent:
        async def handle_request(self, req):
            raise RuntimeError("simulated orchestrator blowup")

    with patch.object(main_module, "report_agent", new=BrokenReportAgent()):
        with patch(
            "backend.pulse.scheduler.ws_manager.broadcast",
            new=AsyncMock(side_effect=_capture),
        ):
            run = await fresh_scheduler.run_once("anything", trigger_source="manual")

    assert run["status"] == "error"
    assert "simulated orchestrator blowup" in (run["error_message"] or "")

    rows = await load_pulse_runs(limit=10)
    assert len(rows) == 1
    assert rows[0]["status"] == "error"
    assert rows[0]["agents_involved"] == 0

    event_types = [e.event_type for e in captured_events]
    assert EventType.PULSE_RUN_STARTED in event_types
    assert EventType.PULSE_RUN_FAILED in event_types


# ============================================================
# 5. Scheduler status shape
# ============================================================

def test_status_shape(fresh_scheduler):
    """status() must return all keys the frontend expects, pre-first-run."""
    status = fresh_scheduler.status()
    expected_keys = {
        "enabled",
        "running",
        "interval_seconds",
        "initial_delay_seconds",
        "watchlist_size",
        "watchlist_next_index",
        "run_count",
        "last_run_at",
        "next_run_at",
        "seconds_since_last_run",
    }
    assert expected_keys.issubset(status.keys())
    assert status["run_count"] == 0
    assert status["last_run_at"] is None
    assert status["seconds_since_last_run"] is None
    assert status["watchlist_size"] >= 1


# ============================================================
# 6. Status is updated after a run
# ============================================================

@pytest.mark.asyncio
async def test_status_updates_after_run(tmp_db, fresh_scheduler):
    """run_count and last_run_at must update after a successful run."""
    import backend.main as main_module

    with patch.object(
        main_module,
        "report_agent",
        new=type("X", (), {"handle_request": AsyncMock(return_value=FAKE_REPORT)})(),
    ):
        with patch(
            "backend.pulse.scheduler.ws_manager.broadcast", new=AsyncMock()
        ):
            await fresh_scheduler.run_once("q1", trigger_source="manual")
            await fresh_scheduler.run_once("q2", trigger_source="manual")

    status = fresh_scheduler.status()
    assert status["run_count"] == 2
    assert status["last_run_at"] is not None
    assert status["seconds_since_last_run"] is not None
    assert status["seconds_since_last_run"] >= 0

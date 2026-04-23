"""
Tests for the Market Pulse autonomous-trigger scheduler (v2).

v2 adds LLM-generated queries + rich payment-detail persistence. These
tests exercise the pulse pipeline WITHOUT hitting the chain, the LLM,
or the real orchestrator — `report_agent.handle_request` and
`llm_router.generate` are mocked, `ws_manager.broadcast` is patched to
a capture list. DB writes go to a temporary SQLite file so test state
is isolated per run.
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio


# ============================================================
# Fixtures
# ============================================================

@pytest_asyncio.fixture
async def tmp_db(monkeypatch):
    """Fresh SQLite file per test. Schema initialized. File removed on exit."""
    fd, path = tempfile.mkstemp(prefix="nexus-pulse-test-", suffix=".db")
    os.close(fd)

    import backend.db as db_mod
    monkeypatch.setattr(db_mod, "DB_PATH", path)
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
    """New PulseScheduler instance per test for clean counter state."""
    from backend.pulse.scheduler import PulseScheduler
    return PulseScheduler()


# A realistic v2 report dict with rich transaction detail.
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
            {
                "from": "Nexus-ReportAgent-v1",
                "to": "Nexus-DataAgent-v1",
                "amount": 0.0001,
                "purpose": "price_data",
                "tx_hash": "0xaa" + "11" * 31,
                "status": "confirmed",
            },
            {
                "from": "Nexus-ReportAgent-v1",
                "to": "Nexus-AuditAgent-v1",
                "amount": 0.0002,
                "purpose": "quality_audit",
                "tx_hash": "0xbb" + "22" * 31,
                "status": "confirmed",
            },
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
# 1. Watchlist fallback pool is intact (v2 uses it only as last resort)
# ============================================================

def test_builtin_fallback_pool_has_entries():
    """Built-in fallback pool must have at least one entry so the
    last-resort path is functional on a fresh install."""
    from backend.pulse.watchlist import BUILT_IN_FALLBACK
    assert len(BUILT_IN_FALLBACK) >= 1
    for q in BUILT_IN_FALLBACK:
        assert isinstance(q, str) and len(q) > 8


# ============================================================
# 2. run_once persists a row with rich payment detail
# ============================================================

@pytest.mark.asyncio
async def test_run_once_persists_row_with_rich_payments(tmp_db, fresh_scheduler):
    """A successful run_once writes a full row + rich per-payment detail."""
    from backend.pulse.store import load_pulse_runs
    import backend.main as main_module

    with patch.object(
        main_module,
        "report_agent",
        new=type("X", (), {"handle_request": AsyncMock(return_value=FAKE_REPORT)})(),
    ):
        with patch(
            "backend.pulse.scheduler.ws_manager.broadcast", new=AsyncMock()
        ):
            run = await fresh_scheduler.run_once(
                "BTC sentiment and price trend last 1h",
                trigger_source="scheduled",
                query_source="llm_generated",
            )

    assert run["status"] == "ok"
    assert run["agents_involved"] == 3
    assert run["query_source"] == "llm_generated"
    assert run["audit_tx_hash"] == "0xcc" + "33" * 31
    assert run["mandate_id"] == "mnd-test-xyz"

    rows = await load_pulse_runs(limit=10)
    assert len(rows) == 1
    row = rows[0]

    # v2: payments field is list[dict], not list[str]
    assert isinstance(row["payments"], list)
    assert len(row["payments"]) == 2

    payment = row["payments"][0]
    assert payment["from_agent"] == "Nexus-ReportAgent-v1"
    assert payment["to_agent"] == "Nexus-DataAgent-v1"
    assert payment["amount"] == pytest.approx(0.0001)
    assert payment["purpose"] == "price_data"
    assert payment["tx_hash"] == "0xaa" + "11" * 31
    assert payment["status"] == "confirmed"


# ============================================================
# 3. Broadcast events include query_source
# ============================================================

@pytest.mark.asyncio
async def test_run_once_emits_events_with_query_source(tmp_db, fresh_scheduler):
    """Happy path emits START + COMPLETE events, both carry query_source."""
    import backend.main as main_module
    from backend.models.events import EventType

    captured: list = []

    async def _capture(event):
        captured.append(event)

    with patch.object(
        main_module,
        "report_agent",
        new=type("X", (), {"handle_request": AsyncMock(return_value=FAKE_REPORT)})(),
    ):
        with patch(
            "backend.pulse.scheduler.ws_manager.broadcast",
            new=AsyncMock(side_effect=_capture),
        ):
            await fresh_scheduler.run_once(
                "test q", trigger_source="manual", query_source="llm_generated",
            )

    types = [e.event_type for e in captured]
    assert EventType.PULSE_RUN_STARTED in types
    assert EventType.PULSE_RUN_COMPLETED in types
    assert types.index(EventType.PULSE_RUN_STARTED) < types.index(
        EventType.PULSE_RUN_COMPLETED
    )
    # Both events carry the query_source tag
    for e in captured:
        if e.event_type in (EventType.PULSE_RUN_STARTED,
                            EventType.PULSE_RUN_COMPLETED):
            assert e.data.get("query_source") == "llm_generated"


# ============================================================
# 4. Failure handling — error row + FAILED event, scheduler doesn't crash
# ============================================================

@pytest.mark.asyncio
async def test_run_once_handles_orchestrator_failure(tmp_db, fresh_scheduler):
    """If handle_request raises, row is persisted with status=error."""
    from backend.pulse.store import load_pulse_runs
    from backend.models.events import EventType
    import backend.main as main_module

    captured: list = []

    async def _capture(event):
        captured.append(event)

    class Broken:
        async def handle_request(self, req):
            raise RuntimeError("simulated blowup")

    with patch.object(main_module, "report_agent", new=Broken()):
        with patch(
            "backend.pulse.scheduler.ws_manager.broadcast",
            new=AsyncMock(side_effect=_capture),
        ):
            run = await fresh_scheduler.run_once(
                "anything", trigger_source="manual", query_source="capability_registry",
            )

    assert run["status"] == "error"
    assert "simulated blowup" in (run["error_message"] or "")
    assert run["query_source"] == "capability_registry"

    rows = await load_pulse_runs(limit=10)
    assert len(rows) == 1
    assert rows[0]["status"] == "error"

    types = [e.event_type for e in captured]
    assert EventType.PULSE_RUN_FAILED in types


# ============================================================
# 5. Status shape (v2: includes last_query_source, no watchlist_next_index)
# ============================================================

def test_status_shape_v2(fresh_scheduler):
    """status() returns all keys the frontend expects."""
    status = fresh_scheduler.status()
    expected = {
        "enabled", "running", "interval_seconds", "initial_delay_seconds",
        "run_count", "last_run_at", "next_run_at", "seconds_since_last_run",
        "last_query_source",
    }
    assert expected.issubset(status.keys())
    assert status["run_count"] == 0
    assert status["last_query_source"] is None
    # v2: the v1 rotation keys must be gone
    assert "watchlist_next_index" not in status
    assert "watchlist_size" not in status


# ============================================================
# 6. Status updates after a run
# ============================================================

@pytest.mark.asyncio
async def test_status_updates_after_run(tmp_db, fresh_scheduler):
    """run_count, last_run_at, last_query_source populated after a run."""
    import backend.main as main_module

    with patch.object(
        main_module,
        "report_agent",
        new=type("X", (), {"handle_request": AsyncMock(return_value=FAKE_REPORT)})(),
    ):
        with patch(
            "backend.pulse.scheduler.ws_manager.broadcast", new=AsyncMock()
        ):
            await fresh_scheduler.run_once("q1", trigger_source="manual",
                                           query_source="llm_generated")
            await fresh_scheduler.run_once("q2", trigger_source="scheduled",
                                           query_source="capability_registry")

    status = fresh_scheduler.status()
    assert status["run_count"] == 2
    assert status["last_run_at"] is not None
    assert status["last_query_source"] == "capability_registry"
    assert status["seconds_since_last_run"] >= 0


# ============================================================
# 7. LLM path — generate_query returns (text, "llm_generated") when LLM works
# ============================================================

@pytest.mark.asyncio
async def test_generate_query_uses_llm_when_available(tmp_db):
    """Happy path: LLM returns valid text → marked llm_generated."""
    from backend.pulse.query_generator import generate_query

    # Stub both the signal fetcher AND the LLM.
    with patch(
        "backend.pulse.query_generator._gather_signals",
        new=AsyncMock(return_value={}),
    ):
        with patch(
            "backend.pulse.query_generator.llm_router.generate",
            new=AsyncMock(return_value="Why is SOL pumping while BTC is flat"),
        ):
            query, source = await generate_query()

    assert source == "llm_generated"
    assert query == "Why is SOL pumping while BTC is flat"


# ============================================================
# 8. Fallback path — LLM fails → capability registry used
# ============================================================

@pytest.mark.asyncio
async def test_generate_query_falls_back_to_registry(tmp_db):
    """LLM raises → fallback to capability_registry example queries."""
    from backend.pulse.query_generator import generate_query

    # Fake registry spec with example queries and positive reputation.
    fake_spec = MagicMock()
    fake_spec.provider_reputation = 75
    fake_spec.example_queries = ["Analyze KITE sentiment comprehensively"]

    with patch(
        "backend.pulse.query_generator._gather_signals",
        new=AsyncMock(return_value={}),
    ):
        with patch(
            "backend.pulse.query_generator.llm_router.generate",
            new=AsyncMock(side_effect=RuntimeError("LLM dead")),
        ):
            with patch(
                "backend.pulse.query_generator.capability_registry.all_specs",
                return_value=[fake_spec],
            ):
                query, source = await generate_query()

    assert source == "capability_registry"
    assert query == "Analyze KITE sentiment comprehensively"


# ============================================================
# 9. Multi-line LLM output is rejected
# ============================================================

@pytest.mark.asyncio
async def test_generate_query_rejects_multiline_llm_output(tmp_db):
    """LLM returning multi-line text → reject, fall through to registry."""
    from backend.pulse.query_generator import generate_query

    fake_spec = MagicMock()
    fake_spec.provider_reputation = 50
    fake_spec.example_queries = ["Single-line fallback query for testing"]

    with patch(
        "backend.pulse.query_generator._gather_signals",
        new=AsyncMock(return_value={}),
    ):
        with patch(
            "backend.pulse.query_generator.llm_router.generate",
            new=AsyncMock(return_value="line one\nline two\nline three"),
        ):
            with patch(
                "backend.pulse.query_generator.capability_registry.all_specs",
                return_value=[fake_spec],
            ):
                query, source = await generate_query()

    assert source == "capability_registry"
    assert "\n" not in query


# ============================================================
# 10. Last-resort fallback — no LLM, no registry → built-in
# ============================================================

@pytest.mark.asyncio
async def test_generate_query_last_resort_builtin(tmp_db):
    """No LLM + empty registry → built-in fallback pool."""
    from backend.pulse.query_generator import generate_query
    from backend.pulse.watchlist import BUILT_IN_FALLBACK

    with patch(
        "backend.pulse.query_generator._gather_signals",
        new=AsyncMock(return_value={}),
    ):
        with patch(
            "backend.pulse.query_generator.llm_router.generate",
            new=AsyncMock(side_effect=RuntimeError("LLM dead")),
        ):
            with patch(
                "backend.pulse.query_generator.capability_registry.all_specs",
                return_value=[],
            ):
                query, source = await generate_query()

    assert source == "built_in_fallback"
    assert query in BUILT_IN_FALLBACK


# ============================================================
# 11. Store: rich v2 format round-trips correctly
# ============================================================

@pytest.mark.asyncio
async def test_store_parses_new_rich_format(tmp_db):
    """Write a row with rich payment list; load back preserves structure."""
    from backend.pulse.store import save_pulse_run, load_pulse_runs

    payments = [
        {"from_agent": "A", "to_agent": "B", "amount": 0.0001,
         "purpose": "data", "tx_hash": "0xabc", "status": "confirmed"},
        {"from_agent": "A", "to_agent": "C", "amount": 0.0002,
         "purpose": "audit", "tx_hash": "0xdef", "status": "confirmed"},
    ]
    await save_pulse_run({
        "run_id": "pulse-v2test",
        "query": "test query",
        "trigger_source": "scheduled",
        "status": "ok",
        "agents_involved": 2,
        "total_cost_usdc": 0.0003,
        "total_time_ms": 1000,
        "audit_tx_hash": "0xaudit",
        "payment_tx_hashes_json": json.dumps(payments),
        "mandate_id": "mnd-v2",
        "started_at": "2026-04-23T12:00:00+00:00",
        "completed_at": "2026-04-23T12:00:01+00:00",
    })

    rows = await load_pulse_runs(limit=10)
    assert len(rows) == 1
    assert rows[0]["payments"] == payments  # exact round-trip


# ============================================================
# 12. Store: v1 legacy string[] format is wrapped into minimal dicts
# ============================================================

@pytest.mark.asyncio
async def test_store_parses_legacy_string_format(tmp_db):
    """Old rows with list[str] tx hashes still load as list[dict]."""
    from backend.pulse.store import save_pulse_run, load_pulse_runs

    legacy_hashes = ["0xoldhash1", "0xoldhash2"]
    await save_pulse_run({
        "run_id": "pulse-v1legacy",
        "query": "legacy query",
        "trigger_source": "scheduled",
        "status": "ok",
        "agents_involved": 2,
        "total_cost_usdc": 0.0003,
        "total_time_ms": 1000,
        "audit_tx_hash": "0xaudit",
        "payment_tx_hashes_json": json.dumps(legacy_hashes),
        "mandate_id": "mnd-v1",
        "started_at": "2026-04-20T12:00:00+00:00",
        "completed_at": "2026-04-20T12:00:01+00:00",
    })

    rows = await load_pulse_runs(limit=10)
    assert len(rows) == 1
    payments = rows[0]["payments"]
    assert len(payments) == 2
    # Each legacy string wrapped as a minimal dict
    assert payments[0] == {
        "from_agent": "", "to_agent": "", "amount": 0.0,
        "purpose": "", "tx_hash": "0xoldhash1", "status": "confirmed",
    }
    assert payments[1]["tx_hash"] == "0xoldhash2"

"""
Tests for marketplace.probe — generic health-check that prevents paying
a dead endpoint. Works for any agent with any /health URL.
"""

import asyncio
import pytest
from backend.marketplace.probe import AgentProber, ProbeResult


@pytest.mark.asyncio
async def test_in_process_agents_always_reachable():
    prober = AgentProber()
    result = await prober.probe("in-proc", callback_url=None)
    assert result.reachable


@pytest.mark.asyncio
async def test_unreachable_host():
    prober = AgentProber(timeout_seconds=0.5)
    # Reserved port that should always refuse
    result = await prober.probe("nobody", callback_url="http://127.0.0.1:1/invoke")
    assert not result.reachable
    assert result.error is not None


@pytest.mark.asyncio
async def test_cache_within_ttl():
    """A second probe within TTL should reuse the cached result."""
    prober = AgentProber(ttl_seconds=30.0, timeout_seconds=0.5)
    r1 = await prober.probe("x", callback_url="http://127.0.0.1:1/invoke")
    r2 = await prober.probe("x", callback_url="http://127.0.0.1:1/invoke")
    # Cache hit means identical object (same timestamp)
    assert r1.checked_at == r2.checked_at


@pytest.mark.asyncio
async def test_force_bypasses_cache():
    prober = AgentProber(ttl_seconds=30.0, timeout_seconds=0.5)
    r1 = await prober.probe("y", callback_url="http://127.0.0.1:1/invoke")
    await asyncio.sleep(0.05)
    r2 = await prober.probe("y", callback_url="http://127.0.0.1:1/invoke", force=True)
    assert r1.checked_at != r2.checked_at


def test_health_url_derivation():
    assert AgentProber._health_url_from("http://localhost:5003/invoke") == "http://localhost:5003/health"
    assert AgentProber._health_url_from("http://x/") == "http://x/health"
    assert AgentProber._health_url_from("http://x/custom") == "http://x/custom/health"

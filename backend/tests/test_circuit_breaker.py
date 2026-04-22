"""
Tests for the Verified Intent circuit breaker system.
Validates that the 7-point payment validation works correctly.
"""

import pytest
import asyncio
from backend.verified_intent.mandate_manager import MandateManager
from backend.verified_intent.circuit_breaker import CircuitBreaker


def _run(coro):
    """Helper to run async code in sync tests."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_mandate_creation_calculates_budget():
    """Mandate budget = sum(agent_prices) * multiplier."""
    mm = MandateManager()
    mandate = mm.create_mandate(
        query="Analyze KITE",
        allowed_agents=["Nexus-DataAgent-v1", "Nexus-AnalystAgent-v1"],
        agent_prices={"Nexus-DataAgent-v1": 0.0001, "Nexus-AnalystAgent-v1": 0.0002},
        budget_multiplier=3.0,
    )
    assert mandate.mandate_id.startswith("mnd-")
    assert mandate.total_budget == round(0.0003 * 3.0, 6)  # 0.0009
    assert mandate.max_per_tx == round(0.0002 * 2, 6)  # 0.0004
    assert len(mandate.allowed_agents) == 2


def test_mandate_creation_signs_with_key():
    """Mandates should be signed when deployer key is available."""
    mm = MandateManager()
    mandate = mm.create_mandate(
        query="test",
        allowed_agents=["AgentA"],
        agent_prices={"AgentA": 0.0001},
    )
    if mm._has_signing_key:
        assert mandate.signature != "unsigned"
        assert mandate.signer_address.startswith("0x")
    else:
        assert mandate.signature == "unsigned"


def test_mandate_validation():
    """Valid mandate should pass validation."""
    mm = MandateManager()
    mandate = mm.create_mandate(
        query="test",
        allowed_agents=["AgentA"],
        agent_prices={"AgentA": 0.0001},
    )
    valid, reason = mm.validate_mandate(mandate.mandate_id)
    assert valid is True
    assert reason == "Valid"


def test_mandate_not_found():
    """Non-existent mandate should fail validation."""
    mm = MandateManager()
    valid, reason = mm.validate_mandate("mnd-nonexistent")
    assert valid is False
    assert "not found" in reason.lower()


def test_circuit_breaker_approves_valid_payment():
    """Valid payment within budget should be approved."""
    mm = MandateManager()
    cb = CircuitBreaker(mm)
    mandate = mm.create_mandate(
        query="test",
        allowed_agents=["AgentA"],
        agent_prices={"AgentA": 0.0001},
    )
    result = _run(cb.check_payment(mandate.mandate_id, "AgentA", 0.0001, 50))
    assert result.approved is True


def test_circuit_breaker_blocks_budget_exceeded():
    """Payment exceeding remaining budget should be blocked."""
    mm = MandateManager()
    cb = CircuitBreaker(mm)
    mandate = mm.create_mandate(
        query="test",
        allowed_agents=["AgentA"],
        agent_prices={"AgentA": 0.0001},
        budget_multiplier=1.0,
    )
    # Spend the entire budget
    mm.record_payment(mandate.mandate_id, "AgentA", 0.0001, "test")
    # Next payment should be blocked
    result = _run(cb.check_payment(mandate.mandate_id, "AgentA", 0.0001, 50))
    assert result.approved is False
    assert "budget" in result.verdict.value.lower()


def test_circuit_breaker_blocks_unknown_agent():
    """Payment to agent not in allowed list should be blocked."""
    mm = MandateManager()
    cb = CircuitBreaker(mm)
    mandate = mm.create_mandate(
        query="test",
        allowed_agents=["AgentA"],
        agent_prices={"AgentA": 0.0001},
    )
    result = _run(cb.check_payment(mandate.mandate_id, "UnknownAgent", 0.0001, 50))
    assert result.approved is False
    assert "not_allowed" in result.verdict.value.lower()


def test_circuit_breaker_blocks_low_reputation():
    """Payment to agent below minimum reputation should be blocked."""
    mm = MandateManager()
    cb = CircuitBreaker(mm)
    mandate = mm.create_mandate(
        query="test",
        allowed_agents=["AgentA"],
        agent_prices={"AgentA": 0.0001},
    )
    # Reputation 10 is below default min_reputation of 20
    result = _run(cb.check_payment(mandate.mandate_id, "AgentA", 0.0001, 10))
    assert result.approved is False
    assert "reputation" in result.verdict.value.lower()


def test_circuit_breaker_blocks_per_tx_exceeded():
    """Payment exceeding per-transaction limit (but within budget) should be blocked."""
    mm = MandateManager()
    cb = CircuitBreaker(mm)
    # Generous budget, but max_per_tx = 0.0001 * 2 = 0.0002
    # So a 0.00025 payment exceeds per_tx but NOT budget (3 * 0.0001 = 0.0003 total budget)
    mandate = mm.create_mandate(
        query="test",
        allowed_agents=["AgentA"],
        agent_prices={"AgentA": 0.0001},
        budget_multiplier=10.0,  # big budget so we only trip per_tx limit
    )
    # max_per_tx = 0.0002, payment of 0.00025 exceeds per_tx but not budget (0.001 total)
    result = _run(cb.check_payment(mandate.mandate_id, "AgentA", 0.00025, 50))
    assert result.approved is False
    assert "per_tx" in result.verdict.value.lower()


def test_mandate_payment_recording():
    """Payments should be tracked against mandate budget."""
    mm = MandateManager()
    mandate = mm.create_mandate(
        query="test",
        allowed_agents=["AgentA", "AgentB"],
        agent_prices={"AgentA": 0.0001, "AgentB": 0.0002},
    )
    mm.record_payment(mandate.mandate_id, "AgentA", 0.0001, "data_collection")
    assert abs(mandate.cumulative_spent - 0.0001) < 1e-9
    assert len(mandate.payment_log) == 1

    mm.record_payment(mandate.mandate_id, "AgentB", 0.0002, "analysis")
    assert abs(mandate.cumulative_spent - 0.0003) < 1e-9
    assert len(mandate.payment_log) == 2


def test_mandate_completion():
    """Completed mandates should move to history."""
    mm = MandateManager()
    mandate = mm.create_mandate(
        query="test",
        allowed_agents=["AgentA"],
        agent_prices={"AgentA": 0.0001},
    )
    mid = mandate.mandate_id
    assert mid in mm.active_mandates

    mm.complete_mandate(mid)
    assert mid not in mm.active_mandates
    assert any(m.mandate_id == mid for m in mm.completed_mandates)

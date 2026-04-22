"""
Tests for ECDSA mandate signing.
Verifies that mandates are properly signed with the deployer key
and that signatures can be validated.
"""

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct

from backend.verified_intent.mandate_manager import MandateManager
from backend.config import settings


def test_mandate_has_valid_ecdsa_signature():
    """Mandates should have real ECDSA signatures when deployer key is set."""
    mm = MandateManager()
    mandate = mm.create_mandate(
        query="Analyze KITE token sentiment",
        allowed_agents=["Nexus-DataAgent-v1"],
        agent_prices={"Nexus-DataAgent-v1": 0.0001},
    )
    if mm._has_signing_key:
        assert mandate.signature != "unsigned"
        assert mandate.signer_address.startswith("0x")
        assert len(mandate.signature) > 20
    else:
        assert mandate.signature == "unsigned"
        assert mandate.signer_address == "local_mode"


def test_signature_recovers_to_deployer_address():
    """The ECDSA signature should recover to the deployer's address."""
    if not settings.deployer_private_key:
        pytest.skip("No deployer key configured")

    mm = MandateManager()
    mandate = mm.create_mandate(
        query="Test query",
        allowed_agents=["TestAgent"],
        agent_prices={"TestAgent": 0.0001},
    )

    # Reconstruct the signed message
    message_text = (
        f"NEXUS_MANDATE:{mandate.mandate_id}:{mandate.context_hash}:"
        f"{mandate.total_budget}:{mandate.max_per_tx}:{mandate.expires_at.isoformat()}"
    )
    message = encode_defunct(text=message_text)

    # Recover signer from signature (strip 0x prefix if present)
    sig_hex = mandate.signature[2:] if mandate.signature.startswith("0x") else mandate.signature
    signature_bytes = bytes.fromhex(sig_hex)
    recovered = Account.recover_message(message, signature=signature_bytes)

    expected = Account.from_key(settings.deployer_private_key).address
    assert recovered == expected
    assert mandate.signer_address == expected


def test_context_hash_is_deterministic():
    """Same query should produce same context hash."""
    mm = MandateManager()
    m1 = mm.create_mandate(
        query="Analyze KITE",
        allowed_agents=["A"],
        agent_prices={"A": 0.0001},
    )
    m2 = mm.create_mandate(
        query="Analyze KITE",
        allowed_agents=["A"],
        agent_prices={"A": 0.0001},
    )
    assert m1.context_hash == m2.context_hash


def test_different_queries_different_hashes():
    """Different queries should produce different context hashes."""
    mm = MandateManager()
    m1 = mm.create_mandate(
        query="Analyze KITE",
        allowed_agents=["A"],
        agent_prices={"A": 0.0001},
    )
    m2 = mm.create_mandate(
        query="Analyze BTC",
        allowed_agents=["A"],
        agent_prices={"A": 0.0001},
    )
    assert m1.context_hash != m2.context_hash


def test_mandate_ids_are_unique():
    """Every mandate should get a unique ID."""
    mm = MandateManager()
    ids = set()
    for _ in range(10):
        m = mm.create_mandate(
            query="test",
            allowed_agents=["A"],
            agent_prices={"A": 0.0001},
        )
        ids.add(m.mandate_id)
    assert len(ids) == 10

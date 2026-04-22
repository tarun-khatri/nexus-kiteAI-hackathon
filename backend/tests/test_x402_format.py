"""
Tests that x402 402 responses match Kite's exact specification.
Ref: https://docs.gokite.ai/kite-agent-passport/service-provider-guide
"""

import pytest
from backend.x402.types import X402AcceptItem, X402PaymentRequired, X402OutputSchema


def test_402_response_has_all_required_fields():
    """Verify 402 response matches Kite weather API format exactly."""
    accept = X402AcceptItem(
        maxAmountRequired="100000000000000",
        resource="http://localhost:8000/x402/data-agent",
        description="Test agent service",
        payTo="0xaa7144D792d7c87aA72fb3EdC16c982654272036",
        merchantName="Nexus-DataAgent-v1",
        outputSchema=X402OutputSchema(),
    )
    response = X402PaymentRequired(accepts=[accept])
    data = response.model_dump()

    # Top-level fields
    assert data["x402Version"] == 1
    assert data["error"] == "X-PAYMENT header is required"
    assert len(data["accepts"]) == 1

    # Accept item fields per Kite spec
    item = data["accepts"][0]
    assert item["scheme"] == "gokite-aa"
    assert item["network"] == "kite-testnet"
    assert item["asset"] == "0x0fF5393387ad2f9f691FD6Fd28e07E3969e27e63"
    assert item["maxTimeoutSeconds"] == 300
    assert item["mimeType"] == "application/json"
    assert item["outputSchema"] is not None
    assert "payTo" in item
    assert "maxAmountRequired" in item
    assert "resource" in item
    assert "merchantName" in item


def test_402_amount_is_string_wei():
    """Kite spec requires maxAmountRequired as string (wei format)."""
    accept = X402AcceptItem(
        maxAmountRequired="100000000000000",
        resource="test",
        description="test",
        payTo="0x0000000000000000000000000000000000000000",
        merchantName="test",
    )
    assert isinstance(accept.maxAmountRequired, str)
    assert accept.maxAmountRequired == "100000000000000"


def test_402_uses_correct_kite_testnet_token():
    """Verify the asset is Kite's official Test USDT address."""
    accept = X402AcceptItem(
        maxAmountRequired="1",
        resource="test",
        description="test",
        payTo="0x0000",
        merchantName="test",
    )
    assert accept.asset == "0x0fF5393387ad2f9f691FD6Fd28e07E3969e27e63"


def test_402_scheme_is_gokite_aa():
    """Kite uses 'gokite-aa' as the payment scheme."""
    accept = X402AcceptItem(
        maxAmountRequired="1",
        resource="test",
        description="test",
        payTo="0x0000",
        merchantName="test",
    )
    assert accept.scheme == "gokite-aa"


def test_output_schema_structure():
    """Verify outputSchema has input and output sections."""
    schema = X402OutputSchema()
    data = schema.model_dump()
    assert "input" in data
    assert "output" in data
    assert data["input"]["discoverable"] is True
    assert data["input"]["type"] == "http"
    assert data["output"]["type"] == "object"


def test_multiple_accepts_supported():
    """Verify response can hold multiple accept items."""
    accepts = [
        X402AcceptItem(
            maxAmountRequired=str(i * 100000000000000),
            resource=f"test/{i}",
            description=f"Agent {i}",
            payTo=f"0x{i:040x}",
            merchantName=f"Agent-{i}",
        )
        for i in range(1, 4)
    ]
    response = X402PaymentRequired(accepts=accepts)
    assert len(response.accepts) == 3

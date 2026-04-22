"""
NEXUS - x402 Protocol Types (Kite-compliant)
Implements the exact data models from Kite's x402 specification.
Ref: https://docs.gokite.ai/kite-agent-passport/service-provider-guide
"""

from pydantic import BaseModel, Field
from typing import Optional

# Kite Testnet Test USDT token address
KITE_TEST_USDT = "0x0fF5393387ad2f9f691FD6Fd28e07E3969e27e63"

# Pieverse facilitator address on Kite Testnet
FACILITATOR_ADDRESS = "0x12343e649e6b2b2b77649DFAb88f103c02F3C78b"

# Facilitator API base URL
FACILITATOR_URL = "https://facilitator.pieverse.io"


class X402OutputSchema(BaseModel):
    """Schema describing service input/output"""
    input: dict = Field(default_factory=lambda: {
        "discoverable": True,
        "method": "POST",
        "type": "http",
    })
    output: dict = Field(default_factory=lambda: {
        "properties": {},
        "required": [],
        "type": "object",
    })


class X402AcceptItem(BaseModel):
    """Single payment option in the 402 response (Kite x402 spec)"""
    scheme: str = "gokite-aa"
    network: str = "kite-testnet"
    maxAmountRequired: str = Field(description="Amount in wei (string)")
    resource: str = Field(description="The API endpoint being paid for")
    description: str = Field(description="Human-readable service description")
    payTo: str = Field(description="Wallet address to receive payment")
    maxTimeoutSeconds: int = 300
    asset: str = KITE_TEST_USDT
    merchantName: str = Field(description="Agent/service name")
    mimeType: str = "application/json"
    outputSchema: Optional[X402OutputSchema] = None
    extra: Optional[str] = None


class X402PaymentRequired(BaseModel):
    """HTTP 402 Payment Required response body (Kite x402 spec)"""
    error: str = "X-PAYMENT header is required"
    accepts: list[X402AcceptItem]
    x402Version: int = 1


class X402Authorization(BaseModel):
    """Payment authorization inside X-PAYMENT header"""
    payer: str = Field(description="Payer wallet address")
    payee: str = Field(description="Payee wallet address")
    amount: str = Field(description="Amount in wei")
    token: str = KITE_TEST_USDT
    network: str = "kite-testnet"
    nonce: str = ""
    validUntil: int = 0


class X402PaymentPayload(BaseModel):
    """The full X-PAYMENT header payload (base64 decoded)"""
    authorization: X402Authorization
    signature: str = Field(description="ECDSA signature of authorization")

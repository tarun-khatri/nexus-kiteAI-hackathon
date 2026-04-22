"""
NEXUS - Kite x402 Payment Client (Agent Treasury Model)

Implements Kite's MCP payment tools (get_payer_addr, approve_payment) for
autonomous agent-to-agent payments on Kite chain.

This follows Kite's "Developer as End User" integration pattern (Mode 2):
  - A treasury wallet (deployer) funds all agent-to-agent payments
  - Agents transact autonomously using signed x402 payloads
  - Each payment settles via the Pieverse facilitator on Kite testnet
  - No individual user Portal sessions needed for autonomous agent operation

The payload format is identical to Kite's MCP server output:
  {authorization: {payer, payee, amount, token, network, nonce, validUntil}, signature}
  -> base64 encoded as X-PAYMENT header

Ref: https://docs.gokite.ai/kite-agent-passport/developer-guide
Kite MCP Server: https://neo.dev.gokite.ai/v1/mcp
"""

import json
import time
import base64
from eth_account import Account
from eth_account.messages import encode_defunct

from backend.config import settings
from backend.x402.types import KITE_TEST_USDT


class KiteMCPClient:
    """
    Client implementing Kite's MCP payment tools for autonomous agent payments.
    Produces x402-compliant X-PAYMENT payloads for the Pieverse facilitator.
    """

    MCP_URL = "https://neo.dev.gokite.ai/v1/mcp"

    def __init__(self):
        self._deployer_address = None
        self._mode = "disconnected"
        if settings.deployer_private_key:
            account = Account.from_key(settings.deployer_private_key)
            self._deployer_address = account.address
            self._mode = "agent_treasury"

    async def get_payer_addr(self) -> dict:
        """
        Kite MCP Tool: get_payer_addr
        Returns the treasury wallet address that funds autonomous agent payments.
        Ref: https://docs.gokite.ai/kite-agent-passport/developer-guide#tool-get_payer_addr
        """
        return {
            "payer_addr": self._deployer_address or "0x" + "0" * 40,
            "mode": self._mode,
            "mcp_server": self.MCP_URL,
        }

    async def approve_payment(
        self,
        payer_addr: str,
        payee_addr: str,
        amount: str,
        token_type: str = "USDC",
        merchant_name: str = "",
    ) -> dict:
        """
        Kite MCP Tool: approve_payment
        Creates a signed X-Payment payload for the x402 protocol.
        Produces x402-compliant payload: {authorization, signature} -> base64 X-PAYMENT header.
        Ref: https://docs.gokite.ai/kite-agent-passport/developer-guide#tool-approve_payment
        """
        if not settings.deployer_private_key:
            return {"error": "No signing key available - configure DEPLOYER_PRIVATE_KEY"}

        authorization = {
            "payer": payer_addr,
            "payee": payee_addr,
            "amount": amount,
            "token": KITE_TEST_USDT,
            "network": "kite-testnet",
            "nonce": str(int(time.time())),
            "validUntil": int(time.time()) + 300,
        }

        # Sign authorization with treasury key (EIP-191)
        message_text = json.dumps(authorization, sort_keys=True)
        message = encode_defunct(text=message_text)
        signed = Account.sign_message(message, private_key=settings.deployer_private_key)
        signature = "0x" + signed.signature.hex()

        # Build X-PAYMENT payload (base64-encoded JSON per x402 spec)
        payload = {"authorization": authorization, "signature": signature}
        x_payment = base64.b64encode(json.dumps(payload).encode()).decode()

        return {
            "x_payment": x_payment,
            "authorization": authorization,
            "signature": signature,
            "mode": self._mode,
            "merchant_name": merchant_name,
        }


# Global singleton
kite_mcp_client = KiteMCPClient()

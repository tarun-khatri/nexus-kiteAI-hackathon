"""
NEXUS - Pieverse Facilitator Client
Handles payment verification and settlement via Kite's x402 facilitator.
Ref: https://facilitator.pieverse.io
"""

import httpx
from typing import Optional
from backend.x402.types import FACILITATOR_URL


class FacilitatorClient:
    """
    Client for the Pieverse x402 facilitator.
    Handles verify and settle operations for x402 payments.
    """

    def __init__(self, base_url: str = FACILITATOR_URL):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)

    async def verify(
        self, authorization: dict, signature: str, network: str = "kite-testnet"
    ) -> dict:
        """
        Verify a payment signature via the facilitator.
        POST /v2/verify
        """
        try:
            response = await self.client.post(
                f"{self.base_url}/v2/verify",
                json={
                    "authorization": authorization,
                    "signature": signature,
                    "network": network,
                },
            )
            if response.status_code == 200:
                result = response.json()
                print(f"[x402] Facilitator verify: SUCCESS")
                return {"success": True, "data": result}
            else:
                print(f"[x402] Facilitator verify failed: HTTP {response.status_code} - {response.text[:200]}")
                return {"success": False, "error": f"HTTP {response.status_code}", "detail": response.text[:200]}
        except Exception as e:
            print(f"[x402] Facilitator verify error: {e}")
            return {"success": False, "error": str(e)}

    async def settle(
        self, authorization: dict, signature: str, network: str = "kite-testnet"
    ) -> dict:
        """
        Settle a payment on-chain via the facilitator.
        POST /v2/settle
        Facilitator executes transferWithAuthorization to the payee wallet.
        """
        try:
            response = await self.client.post(
                f"{self.base_url}/v2/settle",
                json={
                    "authorization": authorization,
                    "signature": signature,
                    "network": network,
                },
            )
            if response.status_code == 200:
                result = response.json()
                print(f"[x402] Facilitator settle: SUCCESS")
                return {"success": True, "data": result}
            else:
                print(f"[x402] Facilitator settle failed: HTTP {response.status_code} - {response.text[:200]}")
                return {"success": False, "error": f"HTTP {response.status_code}", "detail": response.text[:200]}
        except Exception as e:
            print(f"[x402] Facilitator settle error: {e}")
            return {"success": False, "error": str(e)}

    async def close(self):
        await self.client.aclose()


# Global singleton
facilitator_client = FacilitatorClient()

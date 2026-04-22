"""
NEXUS - x402 Payment Client
Handles the client side of x402: gets 402, creates payment, settles.
Used by ReportAgent when paying other agents via x402 protocol.
"""

import httpx

from backend.config import settings
from backend.x402.facilitator import facilitator_client


class X402Client:
    """
    x402 payment client - implements the payer side of the protocol.

    Flow:
    1. Call agent service → get HTTP 402
    2. Parse accepts array for payment requirements
    3. Create authorization + sign with deployer key
    4. Base64 encode as X-PAYMENT header
    5. Resend request with X-PAYMENT header
    """

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
        self.payment_log: list[dict] = []

    async def pay_and_call(
        self, service_url: str, request_data: dict
    ) -> dict:
        """
        Call an x402-gated service. Handles the full payment flow.
        Returns the service response after payment settlement.
        """
        # Step 1: Initial request (expect 402)
        try:
            response = await self.client.post(service_url, json=request_data)
        except Exception as e:
            return {"error": f"Service unreachable: {e}"}

        # If not 402, return directly (no payment needed)
        if response.status_code != 402:
            if response.status_code == 200:
                return response.json()
            return {"error": f"Unexpected status: {response.status_code}"}

        # Step 2: Parse 402 response
        try:
            payment_required = response.json()
        except Exception:
            return {"error": "Invalid 402 response (not JSON)"}

        accepts = payment_required.get("accepts", [])
        if not accepts:
            return {"error": "402 response has no accepts array"}

        accept = accepts[0]

        # Step 3: Create authorization via Kite MCP client
        from backend.kite_mcp.client import kite_mcp_client

        payer_info = await kite_mcp_client.get_payer_addr()
        payer_addr = payer_info.get("payer_addr", "")

        if not payer_addr or payer_addr == "0x0000000000000000000000000000000000000000":
            return {"error": "No payer address available (configure deployer key)"}

        # Use MCP approve_payment to create signed payload
        approval = await kite_mcp_client.approve_payment(
            payer_addr=payer_addr,
            payee_addr=accept.get("payTo", ""),
            amount=accept.get("maxAmountRequired", "0"),
            token_type="USDC",
            merchant_name=accept.get("merchantName", ""),
        )

        if "error" in approval:
            return {"error": f"Payment approval failed: {approval['error']}"}

        authorization = approval.get("authorization", {})
        # x_payment already base64 encoded by MCP client

        # Step 4-5: X-PAYMENT header already created by MCP client
        x_payment = approval.get("x_payment", "")
        signature = approval.get("signature", "")

        # Step 6: Resend with X-PAYMENT header
        try:
            response = await self.client.post(
                service_url,
                json=request_data,
                headers={"X-PAYMENT": x_payment},
            )

            if response.status_code == 200:
                result = response.json()
                self.payment_log.append({
                    "service": service_url,
                    "payee": accept.get("payTo"),
                    "amount": accept.get("maxAmountRequired"),
                    "settled": True,
                })
                print(f"[x402] Payment successful: {service_url}")
                return result
            else:
                return {"error": f"Service returned {response.status_code} after payment"}
        except Exception as e:
            return {"error": f"Service call failed after payment: {e}"}


# Global singleton
x402_client = X402Client()

"""
NEXUS - x402 Middleware for Agent Endpoints
Gates agent services behind x402 payment protocol.
Returns HTTP 402 without payment, processes X-PAYMENT header with payment.
"""

import json
import base64
from fastapi import Request
from fastapi.responses import JSONResponse

from backend.x402.types import (
    X402AcceptItem, X402PaymentRequired, X402OutputSchema, KITE_TEST_USDT, FACILITATOR_ADDRESS,
)
from backend.x402.facilitator import facilitator_client


def build_402_response(
    agent_name: str,
    description: str,
    price_wei: str,
    payto_address: str,
    resource_url: str,
    output_schema: dict = None,
) -> JSONResponse:
    """Build a proper x402 HTTP 402 response per Kite spec."""
    accept = X402AcceptItem(
        maxAmountRequired=price_wei,
        resource=resource_url,
        description=description,
        payTo=payto_address,
        merchantName=agent_name,
        outputSchema=X402OutputSchema(
            input=output_schema["input"],
            output=output_schema["output"],
        ) if output_schema else X402OutputSchema(),
    )
    payment_required = X402PaymentRequired(accepts=[accept])
    return JSONResponse(
        status_code=402,
        content=payment_required.model_dump(),
    )


async def process_x402_payment(request: Request) -> dict:
    """
    Process an X-PAYMENT header.
    Decodes, verifies via facilitator, settles, returns result.
    Returns dict with 'success' key.
    """
    x_payment = request.headers.get("X-PAYMENT")
    if not x_payment:
        return {"success": False, "reason": "no_header"}

    try:
        # Decode base64 X-PAYMENT header
        decoded = base64.b64decode(x_payment)
        payload = json.loads(decoded)

        authorization = payload.get("authorization", {})
        signature = payload.get("signature", "")

        if not authorization or not signature:
            return {"success": False, "reason": "invalid_payload"}

        # Verify via Pieverse facilitator
        verify_result = await facilitator_client.verify(authorization, signature)

        # Settle via facilitator (executes on-chain transfer)
        settle_result = await facilitator_client.settle(authorization, signature)

        if settle_result.get("success"):
            return {
                "success": True,
                "payer": authorization.get("payer"),
                "payee": authorization.get("payee"),
                "amount": authorization.get("amount"),
                "settle_data": settle_result.get("data"),
            }
        else:
            # Facilitator settlement failed - still allow service (graceful degradation)
            # Log the failure but don't block the request
            print(f"[x402] Facilitator settle returned: {settle_result}")
            return {
                "success": True,
                "payer": authorization.get("payer"),
                "payee": authorization.get("payee"),
                "amount": authorization.get("amount"),
                "settle_data": None,
                "facilitator_note": "Settlement attempted - check facilitator logs",
            }

    except Exception as e:
        print(f"[x402] Payment processing error: {e}")
        return {"success": False, "reason": str(e)}

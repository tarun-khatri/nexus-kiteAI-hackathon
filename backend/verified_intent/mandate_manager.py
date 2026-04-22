"""
NEXUS - Mandate Manager
Creates, signs, tracks, and validates spending mandates.
Every query gets a cryptographically-signed mandate that bounds agent behavior.
"""

import hashlib
import uuid
from datetime import datetime, timedelta
from typing import Optional

from eth_account import Account
from eth_account.messages import encode_defunct

from backend.config import settings
from backend.models.mandate import Mandate, MandateStatus, MandatePaymentRecord, PaymentRecordStatus


class MandateManager:
    """
    Manages the lifecycle of spending mandates.
    Each mandate is signed with the deployer's private key,
    creating a verifiable chain of authorization.
    """

    def __init__(self):
        self.active_mandates: dict[str, Mandate] = {}
        self.completed_mandates: list[Mandate] = []
        self._has_signing_key = bool(settings.deployer_private_key)

    def create_mandate(
        self,
        query: str,
        allowed_agents: list[str],
        agent_prices: dict[str, float],
        ttl_seconds: int = 300,
        budget_multiplier: float = 3.0,
    ) -> Mandate:
        """
        Auto-generate a Mandate for a user query.
        - total_budget = sum of all agent prices * multiplier
        - max_per_tx = max(individual agent prices) * 2
        - Signs with deployer key (ECDSA)
        """
        mandate_id = f"mnd-{uuid.uuid4().hex[:12]}"
        context_hash = hashlib.sha256(query.encode()).hexdigest()
        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=ttl_seconds)

        total_budget = sum(agent_prices.values()) * budget_multiplier
        max_per_tx = max(agent_prices.values()) * 2 if agent_prices else 0.001

        mandate = Mandate(
            mandate_id=mandate_id,
            query=query,
            context_hash=context_hash,
            total_budget=round(total_budget, 6),
            max_per_tx=round(max_per_tx, 6),
            allowed_agents=allowed_agents,
            ttl_seconds=ttl_seconds,
            min_reputation=20,
            created_at=now,
            expires_at=expires_at,
        )

        # Sign the mandate with deployer's private key
        signature, signer = self._sign_mandate(mandate)
        mandate.signature = signature
        mandate.signer_address = signer

        self.active_mandates[mandate_id] = mandate
        print(f"[Mandate] Created {mandate_id}: budget=${mandate.total_budget:.4f}, TTL={ttl_seconds}s, agents={len(allowed_agents)}")
        return mandate

    def _sign_mandate(self, mandate: Mandate) -> tuple[str, str]:
        """
        Sign mandate data with deployer private key (ECDSA over EIP-191).
        Returns (signature_hex, signer_address).
        """
        if not self._has_signing_key:
            return "unsigned", "local_mode"

        try:
            message_text = (
                f"NEXUS_MANDATE:{mandate.mandate_id}:{mandate.context_hash}:"
                f"{mandate.total_budget}:{mandate.max_per_tx}:{mandate.expires_at.isoformat()}"
            )
            message = encode_defunct(text=message_text)
            signed = Account.sign_message(message, private_key=settings.deployer_private_key)
            account = Account.from_key(settings.deployer_private_key)
            return signed.signature.hex(), account.address
        except Exception as e:
            print(f"[Mandate] Signing failed: {e}")
            return "unsigned", "local_mode"

    def validate_mandate(self, mandate_id: str) -> tuple[bool, str]:
        """Check if mandate exists, is active, and not expired."""
        mandate = self.active_mandates.get(mandate_id)
        if not mandate:
            return False, "Mandate not found"
        if mandate.status != MandateStatus.ACTIVE:
            return False, f"Mandate status is {mandate.status.value}"
        if mandate.is_expired:
            mandate.status = MandateStatus.EXPIRED
            return False, "Mandate has expired"
        return True, "Valid"

    def record_payment(
        self, mandate_id: str, to_agent: str,
        amount: float, purpose: str, tx_hash: str = "",
        status: PaymentRecordStatus = PaymentRecordStatus.SUCCEEDED,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
    ):
        """Record a payment against a mandate. Status defaults to SUCCEEDED for
        back-compat; callers that know the chain tx fired but the downstream
        agent failed should pass status=FAILED_DOWNSTREAM. Probe-blocked payments
        (no chain tx) use BLOCKED_UNREACHABLE and do NOT increment cumulative_spent."""
        mandate = self.active_mandates.get(mandate_id)
        if not mandate:
            return

        # Only count money actually debited on-chain toward the budget.
        if status != PaymentRecordStatus.BLOCKED_UNREACHABLE:
            mandate.cumulative_spent += amount

        mandate.payment_log.append(MandatePaymentRecord(
            to_agent=to_agent,
            amount=amount,
            purpose=purpose,
            tx_hash=tx_hash,
            status=status,
            error_code=error_code,
            error_message=error_message,
        ))

    def mark_payment_failed(
        self, mandate_id: str, tx_hash: str,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        """
        Flip an already-recorded SUCCEEDED payment to FAILED_DOWNSTREAM.
        Used when we paid on-chain, then the agent returned an error.
        Returns True if a matching entry was found and updated.
        """
        mandate = self.active_mandates.get(mandate_id)
        if not mandate or not tx_hash:
            return False
        for rec in reversed(mandate.payment_log):
            if rec.tx_hash == tx_hash and rec.status == PaymentRecordStatus.SUCCEEDED:
                rec.status = PaymentRecordStatus.FAILED_DOWNSTREAM
                rec.error_code = error_code
                rec.error_message = error_message
                return True
        return False

    def complete_mandate(self, mandate_id: str):
        """Mark mandate as completed, move to history."""
        mandate = self.active_mandates.pop(mandate_id, None)
        if mandate:
            mandate.status = MandateStatus.COMPLETED
            self.completed_mandates.append(mandate)
            print(f"[Mandate] Completed {mandate_id}: spent=${mandate.cumulative_spent:.4f}/{mandate.total_budget:.4f}")

            # Persist to SQLite (fire-and-forget since this is sync)
            try:
                import asyncio
                from backend.db import save_mandate
                asyncio.ensure_future(save_mandate({
                    "mandate_id": mandate.mandate_id,
                    "query": mandate.query,
                    "context_hash": mandate.context_hash,
                    "total_budget": mandate.total_budget,
                    "total_spent": mandate.cumulative_spent,
                    "status": mandate.status.value,
                    "signature": mandate.signature,
                    "signer_address": mandate.signer_address,
                }))
            except Exception:
                pass  # DB persistence is best-effort

    def get_mandate(self, mandate_id: str) -> Optional[Mandate]:
        """Retrieve active or completed mandate."""
        mandate = self.active_mandates.get(mandate_id)
        if mandate:
            return mandate
        for m in self.completed_mandates:
            if m.mandate_id == mandate_id:
                return m
        return None


# Global singleton
mandate_manager = MandateManager()

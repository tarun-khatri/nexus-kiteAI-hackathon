"""
NEXUS - Circuit Breaker
Pre-payment validation engine. Checks every payment against the mandate
constraints before allowing it to proceed.
"""

from datetime import datetime

from backend.models.circuit_breaker import CircuitBreakerResult, CircuitBreakerVerdict
from backend.verified_intent.mandate_manager import MandateManager


class CircuitBreaker:
    """
    Stateless validator that gates every payment.
    Runs 5 checks against the mandate before approving.
    """

    def __init__(self, mandate_manager: MandateManager):
        self.mandate_manager = mandate_manager
        self.block_log: list[CircuitBreakerResult] = []
        self.approval_count: int = 0
        self.block_count: int = 0

    async def check_payment(
        self,
        mandate_id: str,
        to_agent: str,
        amount: float,
        agent_reputation: int = 50,
    ) -> CircuitBreakerResult:
        """
        Run all checks in order. Returns CircuitBreakerResult.
        Checks: mandate valid -> budget -> per-tx -> agent allowed -> expired -> reputation
        """
        # Check 1: Mandate exists and is active
        valid, reason = self.mandate_manager.validate_mandate(mandate_id)
        if not valid:
            return self._block(
                CircuitBreakerVerdict.BLOCKED_MANDATE_EXPIRED,
                mandate_id, amount, to_agent,
                f"Mandate invalid: {reason}", 0.0,
            )

        mandate = self.mandate_manager.get_mandate(mandate_id)

        # Check 2: Budget not exceeded
        if mandate.cumulative_spent + amount > mandate.total_budget:
            return self._block(
                CircuitBreakerVerdict.BLOCKED_BUDGET_EXCEEDED,
                mandate_id, amount, to_agent,
                f"Payment ${amount:.4f} would exceed budget (spent: ${mandate.cumulative_spent:.4f}, limit: ${mandate.total_budget:.4f})",
                mandate.budget_remaining,
            )

        # Check 3: Per-transaction limit
        if amount > mandate.max_per_tx:
            return self._block(
                CircuitBreakerVerdict.BLOCKED_PER_TX_EXCEEDED,
                mandate_id, amount, to_agent,
                f"Payment ${amount:.4f} exceeds per-tx limit ${mandate.max_per_tx:.4f}",
                mandate.budget_remaining,
            )

        # Check 4: Agent is in allowed list
        if to_agent not in mandate.allowed_agents:
            return self._block(
                CircuitBreakerVerdict.BLOCKED_AGENT_NOT_ALLOWED,
                mandate_id, amount, to_agent,
                f"Agent '{to_agent}' not in mandate's allowed list",
                mandate.budget_remaining,
            )

        # Check 5: Mandate not expired
        if mandate.is_expired:
            return self._block(
                CircuitBreakerVerdict.BLOCKED_MANDATE_EXPIRED,
                mandate_id, amount, to_agent,
                f"Mandate expired at {mandate.expires_at.isoformat()}",
                mandate.budget_remaining,
            )

        # Check 6: Minimum reputation
        if agent_reputation < mandate.min_reputation:
            return self._block(
                CircuitBreakerVerdict.BLOCKED_LOW_REPUTATION,
                mandate_id, amount, to_agent,
                f"Agent reputation {agent_reputation} below minimum {mandate.min_reputation}",
                mandate.budget_remaining,
            )

        # Check 7: On-chain governance rules (GovernanceRules contract)
        try:
            from backend.blockchain.kite_client import kite_client
            if kite_client.governance_contract:
                on_chain_allowed, on_chain_reason = await kite_client.check_governance(to_agent, amount)
                if not on_chain_allowed:
                    return self._block(
                        CircuitBreakerVerdict.BLOCKED_PER_TX_EXCEEDED,
                        mandate_id, amount, to_agent,
                        f"On-chain governance: {on_chain_reason}",
                        mandate.budget_remaining,
                    )
        except Exception as e:
            # Don't block on governance check failure (fail-open for availability)
            print(f"[CircuitBreaker] On-chain governance check error (continuing): {e}")

        # All checks passed (local + on-chain)
        self.approval_count += 1
        return CircuitBreakerResult(
            approved=True,
            verdict=CircuitBreakerVerdict.APPROVED,
            mandate_id=mandate_id,
            requested_amount=amount,
            to_agent=to_agent,
            detail=f"All checks passed. Budget remaining: ${mandate.budget_remaining - amount:.4f}",
            budget_remaining=mandate.budget_remaining - amount,
        )

    def _block(
        self, verdict: CircuitBreakerVerdict,
        mandate_id: str, amount: float, to_agent: str,
        detail: str, budget_remaining: float,
    ) -> CircuitBreakerResult:
        """Create a block result and log it."""
        self.block_count += 1
        result = CircuitBreakerResult(
            approved=False,
            verdict=verdict,
            mandate_id=mandate_id,
            requested_amount=amount,
            to_agent=to_agent,
            detail=detail,
            budget_remaining=budget_remaining,
        )
        self.block_log.append(result)
        print(f"[CircuitBreaker] BLOCKED: {verdict.value} | {detail}")
        return result


# Global singleton
from backend.verified_intent.mandate_manager import mandate_manager as _mm
circuit_breaker = CircuitBreaker(_mm)

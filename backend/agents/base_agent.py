"""
NEXUS - Base Agent Class
All built-in agents inherit from this base class.
Provides common functionality: identity, payments, events, reputation.
"""

import uuid
import time
import asyncio
from typing import Optional, Any
from datetime import datetime

from backend.models.agent import AgentInfo, AgentStatus
from backend.models.transaction import Transaction, TransactionType, TransactionStatus
from backend.models.events import NexusEvent, EventType
from backend.websocket.manager import ws_manager


class BaseAgent:
    """
    Base class for all Nexus agents.
    Handles identity (Agent Passport), payments (x402), and event emission.
    """

    def __init__(self, agent_id: str, name: str, description: str,
                 capabilities: list[str], price_per_query: float,
                 keywords: Optional[list[str]] = None,
                 example_queries: Optional[list[str]] = None,
                 consumes: Optional[list[str]] = None,
                 provides: Optional[list[str]] = None):
        # Core identity
        self.agent_id = agent_id
        self.name = name
        self.description = description
        self.capabilities = capabilities
        self.price_per_query = price_per_query
        # Self-declared routing metadata (used by DiscoveryEngine).
        # New agents auto-route based on these -- NO code changes needed elsewhere.
        self.keywords: list[str] = keywords or []
        self.example_queries: list[str] = example_queries or []
        # Self-declared data-flow metadata (used by ReportAgent dispatcher).
        # `provides`: data keys this agent's output puts into the shared context
        # `consumes`: data keys this agent expects to find in the shared context
        # Used for topological execution order -- NO hardcoded ordering anywhere.
        self.provides: list[str] = provides or list(capabilities)
        self.consumes: list[str] = consumes or []

        # State
        self.status = AgentStatus.ACTIVE
        self.reputation_score = 50  # Start at 50/100
        self.total_jobs_completed = 0
        self.total_earned = 0.0
        self.total_spent = 0.0

        # Kite blockchain (set during registration)
        self.wallet_address: Optional[str] = None
        self.passport_id: Optional[str] = None

        # Transaction history
        self.transactions: list[Transaction] = []

        # Reputation history (transparent - shows WHY reputation changed)
        self.reputation_history: list[dict] = [{
            "timestamp": datetime.utcnow().isoformat(),
            "old_score": 0,
            "new_score": 50,
            "change": 50,
            "reason": "Initial registration - all agents start at 50/100",
            "direction": "up",
        }]

    def get_info(self) -> AgentInfo:
        """Return agent info as a Pydantic model"""
        return AgentInfo(
            agent_id=self.agent_id,
            name=self.name,
            description=self.description,
            capabilities=self.capabilities,
            price_per_query=self.price_per_query,
            status=self.status,
            reputation_score=self.reputation_score,
            total_jobs_completed=self.total_jobs_completed,
            total_earned=self.total_earned,
            total_spent=self.total_spent,
            wallet_address=self.wallet_address,
            passport_id=self.passport_id,
        )

    async def emit_event(self, event: NexusEvent):
        """Push an event to the dashboard via WebSocket"""
        await ws_manager.broadcast(event)

    async def start_work(self, task_description: str) -> float:
        """Mark agent as busy and return start time"""
        self.status = AgentStatus.BUSY
        await ws_manager.emit_work_started(self.name, task_description)
        return time.time()

    async def complete_work(self, task_description: str, start_time: float) -> float:
        """Mark agent as active, emit completion, return duration"""
        duration_ms = (time.time() - start_time) * 1000
        self.status = AgentStatus.ACTIVE
        self.total_jobs_completed += 1
        await ws_manager.emit_work_completed(self.name, task_description, duration_ms)
        return duration_ms

    async def receive_payment(self, from_agent_name: str, amount: float, purpose: str) -> Transaction:
        """Record an incoming payment"""
        tx = Transaction(
            tx_id=str(uuid.uuid4()),
            from_agent=from_agent_name,
            to_agent=self.name,
            amount=amount,
            tx_type=TransactionType.PAYMENT,
            status=TransactionStatus.CONFIRMED,
            purpose=purpose,
        )
        self.transactions.append(tx)
        self.total_earned += amount
        return tx

    async def make_payment(
        self, to_agent_name: str, amount: float, purpose: str,
        mandate_id: Optional[str] = None,
    ) -> Transaction:
        """
        Execute a REAL x402 payment on Kite chain.
        If mandate_id is provided, the circuit breaker validates the payment first.
        """
        from backend.blockchain.kite_client import kite_client

        # --- Circuit Breaker: validate before paying ---
        if mandate_id:
            from backend.verified_intent.mandate_manager import mandate_manager
            from backend.verified_intent.circuit_breaker import circuit_breaker

            result = await circuit_breaker.check_payment(
                mandate_id, to_agent_name, amount,
                agent_reputation=self.reputation_score,
            )

            # Emit circuit breaker event
            cb_event_type = (
                EventType.CIRCUIT_BREAKER_APPROVED if result.approved
                else EventType.CIRCUIT_BREAKER_BLOCKED
            )
            await ws_manager.broadcast(NexusEvent(
                event_type=cb_event_type,
                agent_id=self.name,
                target_agent_id=to_agent_name,
                data={
                    "approved": result.approved,
                    "verdict": result.verdict.value,
                    "amount": amount,
                    "to_agent": to_agent_name,
                    "detail": result.detail,
                    "budget_remaining": result.budget_remaining,
                    "mandate_id": mandate_id,
                    "reason": result.detail,
                },
                message=(
                    f"Circuit breaker: APPROVED ${amount:.4f} to {to_agent_name}"
                    if result.approved
                    else f"CIRCUIT BREAKER BLOCKED: {result.detail}"
                ),
            ))

            if not result.approved:
                # Payment blocked - return failed transaction
                tx = Transaction(
                    tx_id=str(uuid.uuid4()),
                    from_agent=self.name,
                    to_agent=to_agent_name,
                    amount=amount,
                    tx_type=TransactionType.PAYMENT,
                    status=TransactionStatus.FAILED,
                    purpose=purpose,
                    blocked_reason=result.detail,
                    mandate_id=mandate_id,
                )
                self.transactions.append(tx)
                return tx

        # --- Execute real on-chain payment ---
        tx_hash = await kite_client.pay_for_service(self.name, to_agent_name, amount, purpose)

        tx = Transaction(
            tx_id=tx_hash or str(uuid.uuid4()),
            tx_hash=tx_hash,
            from_agent=self.name,
            to_agent=to_agent_name,
            amount=amount,
            tx_type=TransactionType.PAYMENT,
            status=TransactionStatus.CONFIRMED if tx_hash else TransactionStatus.PENDING,
            purpose=purpose,
            mandate_id=mandate_id,
        )
        self.transactions.append(tx)
        self.total_spent += amount

        # Persist to SQLite
        try:
            from backend.db import save_transaction
            await save_transaction({
                "tx_id": tx.tx_id,
                "from_agent": self.name,
                "to_agent": to_agent_name,
                "amount": amount,
                "purpose": purpose,
                "tx_hash": tx_hash or "",
                "status": tx.status.value,
                "mandate_id": mandate_id or "",
            })
        except Exception:
            pass  # DB persistence is best-effort, never blocks payments

        # Record payment against mandate
        if mandate_id:
            from backend.verified_intent.mandate_manager import mandate_manager
            mandate_manager.record_payment(mandate_id, to_agent_name, amount, purpose, tx_hash or "")

        # Emit payment event to dashboard
        await ws_manager.emit_payment(self.name, to_agent_name, amount, purpose, tx_hash or tx.tx_id)
        return tx

    async def update_reputation(self, change: int, reason: str = ""):
        """Update reputation score locally AND on-chain with transparent history"""
        from backend.blockchain.kite_client import kite_client
        from datetime import datetime, timezone

        old_score = self.reputation_score
        self.reputation_score = max(0, min(100, self.reputation_score + change))

        # Record transparent history
        self.reputation_history.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "old_score": old_score,
            "new_score": self.reputation_score,
            "change": change,
            "reason": reason,
            "direction": "up" if change > 0 else "down" if change < 0 else "unchanged",
        })

        # Update on-chain reputation — capture the tx hash so the UI can link to it.
        tx_hash: str = ""
        if change > 0:
            tx_hash = await kite_client.record_success(self.name, self.reputation_score) or ""
        elif change < 0:
            tx_hash = await kite_client.record_failure(self.name) or ""

        # Persist to SQLite
        try:
            from backend.db import save_reputation_event
            await save_reputation_event(self.name, old_score, self.reputation_score, change, reason)
        except Exception:
            pass  # DB persistence is best-effort

        # Invalidate the agent catalog cache so the next /api/agents poll
        # returns the fresh reputation immediately (not 15-30s stale data).
        try:
            from backend.agent_catalog import agent_catalog
            agent_catalog._chain_cache_at = 0  # force next get_all() to refresh
        except Exception:
            pass

        await ws_manager.emit_reputation_update(
            self.name, old_score, self.reputation_score, tx_hash=tx_hash,
        )

    def has_capability(self, capability: str) -> bool:
        """Check if this agent offers a specific capability"""
        return capability in self.capabilities

    def prepare_request(self, capability: str, context: dict) -> dict:
        """
        Build the request payload this agent expects when invoked for a given
        capability. The orchestrator (ReportAgent) calls this -- it does NOT
        know agent-specific request shapes. Each agent owns its own dispatch.

        Default implementation: pass through capability + query + full context.
        Subclasses override to extract specific fields they need from context.

        `context` always contains:
          - "query": user query / token symbol
          - "outputs": dict mapping agent_id -> previous result dict
          - "provides_index": dict mapping data-key -> [agent_ids that produced it]
        """
        return {
            "type": capability,
            "query": context.get("query", ""),
            "context": context,
        }

    async def handle_request(self, request: dict) -> dict:
        """
        Main entry point for agent work.
        Override in each specific agent subclass.
        """
        raise NotImplementedError("Each agent must implement handle_request()")

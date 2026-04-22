"""
NEXUS - Transaction Data Models
Tracks all x402 payments between agents.
"""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from datetime import datetime, timezone


class TransactionType(str, Enum):
    PAYMENT = "payment"           # Agent pays another agent for service
    REWARD = "reward"             # System rewards agent for good work
    PENALTY = "penalty"           # System penalizes agent for bad work
    REFUND = "refund"             # Payment refunded due to failure


class TransactionStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"                         # Circuit breaker rejected (pre-chain)
    BLOCKED_UNREACHABLE = "blocked_unreachable"  # Probe failed; no on-chain tx fired
    FAILED_DOWNSTREAM = "failed_downstream"   # On-chain tx succeeded but agent returned error/timeout


class Transaction(BaseModel):
    """Represents an x402 payment between agents on Kite chain"""

    tx_id: str = Field(description="Unique transaction ID")
    tx_hash: Optional[str] = Field(default=None, description="Kite chain transaction hash")
    from_agent: str = Field(description="Paying agent ID")
    to_agent: str = Field(description="Receiving agent ID")
    amount: float = Field(description="Amount in USDC")
    tx_type: TransactionType = Field(default=TransactionType.PAYMENT)
    status: TransactionStatus = Field(default=TransactionStatus.PENDING)
    purpose: str = Field(default="", description="What this payment is for")
    blocked_reason: Optional[str] = Field(default=None, description="Reason if blocked by circuit breaker")
    mandate_id: Optional[str] = Field(default=None, description="Associated mandate ID")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def display_amount(self) -> str:
        return f"${self.amount:.4f}"

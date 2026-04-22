"""
NEXUS - Mandate Model
A Mandate defines the cryptographically-signed authorization boundary
for a query. Every agent action must operate within its mandate.
"""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from datetime import datetime


class MandateStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    EXPIRED = "expired"
    BREACHED = "breached"


class PaymentRecordStatus(str, Enum):
    """Lifecycle of a single payment inside a mandate's payment_log."""
    SUCCEEDED = "succeeded"                 # Chain tx confirmed AND agent returned success
    FAILED_DOWNSTREAM = "failed_downstream" # Chain tx confirmed BUT agent returned error/timeout
    BLOCKED_UNREACHABLE = "blocked_unreachable"  # Probe failed; no chain tx fired


class MandatePaymentRecord(BaseModel):
    to_agent: str
    amount: float
    purpose: str
    tx_hash: str = ""
    status: PaymentRecordStatus = PaymentRecordStatus.SUCCEEDED
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class Mandate(BaseModel):
    """
    A signed spending authorization for a single query.
    Defines budget, allowed agents, TTL, and tracks cumulative spend.
    """
    mandate_id: str = Field(description="Unique mandate identifier (mnd-...)")
    query: str = Field(description="Original user query")
    context_hash: str = Field(description="sha256 of the original query")
    total_budget: float = Field(description="Max total USDC for this query")
    max_per_tx: float = Field(description="Max USDC per individual payment")
    allowed_agents: list[str] = Field(description="Agent names allowed to participate")
    ttl_seconds: int = Field(default=300, description="Time-to-live from creation")
    min_reputation: int = Field(default=20, description="Minimum reputation to accept")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime = Field(description="When this mandate expires")
    signature: str = Field(default="unsigned", description="ECDSA signature hex")
    signer_address: str = Field(default="local_mode", description="Address that signed")
    status: MandateStatus = Field(default=MandateStatus.ACTIVE)
    cumulative_spent: float = Field(default=0.0, description="Running total spent")
    payment_log: list[MandatePaymentRecord] = Field(default_factory=list)

    @property
    def budget_remaining(self) -> float:
        return self.total_budget - self.cumulative_spent

    @property
    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expires_at

    @property
    def is_active(self) -> bool:
        return self.status == MandateStatus.ACTIVE and not self.is_expired

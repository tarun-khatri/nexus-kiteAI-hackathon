"""
NEXUS - Circuit Breaker Models
Pre-payment validation results. Every payment must pass the circuit breaker.
"""

from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime


class CircuitBreakerVerdict(str, Enum):
    APPROVED = "approved"
    BLOCKED_BUDGET_EXCEEDED = "blocked_budget_exceeded"
    BLOCKED_PER_TX_EXCEEDED = "blocked_per_tx_exceeded"
    BLOCKED_AGENT_NOT_ALLOWED = "blocked_agent_not_allowed"
    BLOCKED_MANDATE_EXPIRED = "blocked_mandate_expired"
    BLOCKED_LOW_REPUTATION = "blocked_low_reputation"


class CircuitBreakerResult(BaseModel):
    """Result of a circuit breaker pre-payment check"""
    approved: bool
    verdict: CircuitBreakerVerdict
    mandate_id: str
    requested_amount: float
    to_agent: str
    detail: str = Field(description="Human-readable explanation")
    budget_remaining: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)

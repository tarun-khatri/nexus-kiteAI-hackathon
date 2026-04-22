"""
NEXUS - Verified Intent Header
Attached to every agent-to-agent request as cryptographic authorization.
"""

from pydantic import BaseModel, Field
from datetime import datetime


class VerifiedIntentHeader(BaseModel):
    """Signed header proving an agent request is authorized by a mandate"""
    mandate_id: str
    context_hash: str
    signature: str = Field(description="Mandate ECDSA signature proving authorization")
    budget_remaining: float
    requesting_agent: str
    target_agent: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

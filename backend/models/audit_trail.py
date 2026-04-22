"""
NEXUS - Audit Trail Models
Immutable on-chain record linking user intent -> agent actions -> results.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class AuditTrailEntry(BaseModel):
    """On-chain audit trail linking query intent to agent actions and results"""
    trail_id: str
    mandate_id: str
    query: str
    context_hash: str
    traceability_hash: str = Field(description="sha256(query + mandate + actions + payments + report)")
    report_hash: str = Field(description="sha256 of the final report JSON")
    agent_actions: list[dict] = Field(default_factory=list)
    payments: list[dict] = Field(default_factory=list)
    on_chain_tx_hash: Optional[str] = None
    explorer_url: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

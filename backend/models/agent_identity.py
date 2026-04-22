"""
NEXUS - Agent Identity Model
DID-like decentralized identity for each agent, linking to on-chain registry.
"""

from pydantic import BaseModel, Field
from datetime import datetime


class AgentIdentity(BaseModel):
    """Decentralized identity for an agent in the Nexus economy"""
    did: str = Field(description="did:nexus:kite:0x{passport_hex}")
    agent_name: str
    passport_hex: str
    controller: str = Field(description="Deployer wallet address that controls this agent")
    registry_address: str = Field(description="AgentRegistry contract address")
    created_at: datetime = Field(default_factory=datetime.utcnow)

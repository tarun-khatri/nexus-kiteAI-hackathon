"""
NEXUS - Agent Data Models
Defines the structure of an AI agent in the Nexus economy.
"""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from datetime import datetime


class AgentStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    BUSY = "busy"


class AgentCapability(str, Enum):
    TWITTER_DATA = "twitter_data"
    PRICE_DATA = "price_data"
    WHALE_DATA = "whale_data"
    NEWS_DATA = "news_data"
    SENTIMENT_ANALYSIS = "sentiment_analysis"
    PRICE_TREND = "price_trend"
    WHALE_ANALYSIS = "whale_analysis"
    NEWS_SUMMARY = "news_summary"
    REPORT_GENERATION = "report_generation"
    ORCHESTRATION = "orchestration"
    PRICE_ALERTS = "price_alerts"
    SENTIMENT_ALERTS = "sentiment_alerts"
    WHALE_ALERTS = "whale_alerts"
    QUALITY_AUDIT = "quality_audit"
    DATA_VERIFICATION = "data_verification"
    CONSISTENCY_CHECK = "consistency_check"


class AgentInfo(BaseModel):
    """Represents an AI agent in the Nexus economy"""

    agent_id: str = Field(description="Unique agent identifier")
    name: str = Field(description="Human-readable agent name")
    description: str = Field(description="What this agent does")
    capabilities: list[str] = Field(description="List of capabilities this agent offers")
    price_per_query: float = Field(description="Price in USDC per query")
    status: AgentStatus = Field(default=AgentStatus.ACTIVE)
    reputation_score: int = Field(default=50, ge=0, le=100)
    total_jobs_completed: int = Field(default=0)
    total_earned: float = Field(default=0.0)
    total_spent: float = Field(default=0.0)
    wallet_address: Optional[str] = Field(default=None, description="Kite chain wallet address")
    passport_id: Optional[str] = Field(default=None, description="Kite Agent Passport ID")
    registered_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def net_earnings(self) -> float:
        return self.total_earned - self.total_spent


class AgentDiscoveryResult(BaseModel):
    """Result of discovering agents for a capability"""

    capability: str
    agents_found: list[AgentInfo]
    best_agent: Optional[AgentInfo] = None
    selection_reason: str = ""

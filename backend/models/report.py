"""
NEXUS - Report Data Models
Structure for the final intelligence reports.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ReportSection(BaseModel):
    """A section of the report contributed by a specific agent"""

    agent_id: str
    agent_name: str
    section_type: str  # e.g., "sentiment", "price_trend", "whale_activity"
    content: dict
    quality_score: Optional[int] = None  # Set by AuditAgent
    cost: float = 0.0  # How much was paid for this section


class Report(BaseModel):
    """Complete intelligence report assembled by ReportAgent"""

    report_id: str
    query: str = Field(description="Original user query")
    sections: list[ReportSection] = Field(default_factory=list)
    summary: str = Field(default="", description="AI-generated summary")
    verdict: str = Field(default="", description="Overall assessment")
    confidence: str = Field(default="", description="Confidence level")
    total_cost: float = Field(default=0.0, description="Total USDC spent")
    total_time_ms: float = Field(default=0.0, description="Total time in milliseconds")
    agents_involved: int = Field(default=0)
    transactions_count: int = Field(default=0)
    overall_quality_score: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

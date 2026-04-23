"""
NEXUS - Real-Time Event Models
Events that get pushed to the dashboard via WebSocket.
"""

from pydantic import BaseModel, Field
from typing import Optional, Any
from enum import Enum
from datetime import datetime, timezone


class EventType(str, Enum):
    # Agent lifecycle events
    AGENT_REGISTERED = "agent_registered"
    AGENT_STATUS_CHANGE = "agent_status_change"

    # Discovery events
    AGENT_DISCOVERY = "agent_discovery"
    AGENT_SELECTED = "agent_selected"

    # Work events
    WORK_STARTED = "work_started"
    WORK_COMPLETED = "work_completed"
    WORK_FAILED = "work_failed"

    # Payment events
    PAYMENT_SENT = "payment_sent"
    PAYMENT_RECEIVED = "payment_received"
    PAYMENT_CONFIRMED = "payment_confirmed"

    # Audit events
    AUDIT_STARTED = "audit_started"
    AUDIT_COMPLETED = "audit_completed"

    # Reputation events
    REPUTATION_UPDATE = "reputation_update"

    # Report events
    REPORT_STARTED = "report_started"
    REPORT_SECTION_ADDED = "report_section_added"
    REPORT_COMPLETED = "report_completed"

    # Governance events
    GOVERNANCE_RULE_CHANGED = "governance_rule_changed"
    GOVERNANCE_RULE_ENFORCED = "governance_rule_enforced"

    # Alert events
    ALERT_CREATED = "alert_created"
    ALERT_TRIGGERED = "alert_triggered"

    # System events
    SYSTEM_INFO = "system_info"
    SYSTEM_ERROR = "system_error"

    # Verified Intent events
    MANDATE_CREATED = "mandate_created"
    MANDATE_COMPLETED = "mandate_completed"
    CIRCUIT_BREAKER_APPROVED = "circuit_breaker_approved"
    CIRCUIT_BREAKER_BLOCKED = "circuit_breaker_blocked"
    AUDIT_TRAIL_RECORDED = "audit_trail_recorded"
    AGENT_IDENTITY_RESOLVED = "agent_identity_resolved"
    MARKETPLACE_CAPABILITY_MISSING = "marketplace_capability_missing"

    # Market Pulse events (autonomous trigger, no human in loop)
    PULSE_RUN_STARTED = "pulse_run_started"
    PULSE_RUN_COMPLETED = "pulse_run_completed"
    PULSE_RUN_FAILED = "pulse_run_failed"


class NexusEvent(BaseModel):
    """A real-time event in the Nexus economy, pushed to dashboard via WebSocket"""

    event_type: EventType
    agent_id: Optional[str] = None
    target_agent_id: Optional[str] = None
    data: dict = Field(default_factory=dict)
    message: str = Field(default="", description="Human-readable event description")
    # Timezone-aware UTC so isoformat() produces "...+00:00" and browsers
    # in any locale parse the ISO string as UTC correctly.
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )

    def to_ws_message(self) -> dict:
        """Convert to WebSocket message format"""
        return {
            "event": self.event_type.value,
            "agent": self.agent_id,
            "target": self.target_agent_id,
            "data": self.data,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
        }

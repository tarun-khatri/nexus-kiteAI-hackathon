"""
NEXUS - AlertAgent
The Watchdog.

Monitors thresholds and sends notifications:
- Price drop/spike alerts
- Whale activity alerts
- Sentiment shift alerts
- Custom threshold alerts

Price: $0.0001 per alert subscription
"""

import time
import asyncio
from datetime import datetime
from typing import Optional

from backend.agents.base_agent import BaseAgent
from backend.models.events import NexusEvent, EventType
from backend.websocket.manager import ws_manager


class AlertRule:
    """Defines a monitoring rule"""

    def __init__(self, rule_id: str, alert_type: str, token: str,
                 threshold: float, direction: str = "below", callback: str = ""):
        self.rule_id = rule_id
        self.alert_type = alert_type  # price_drop, price_spike, whale, sentiment
        self.token = token
        self.threshold = threshold
        self.direction = direction  # "below" or "above"
        self.callback = callback
        self.triggered = False
        self.created_at = datetime.utcnow()
        self.last_checked = None


class AlertAgent(BaseAgent):
    """
    AlertAgent - Monitors conditions and triggers notifications.
    Watches for price changes, whale activity, and sentiment shifts.
    """

    def __init__(self):
        super().__init__(
            agent_id="alert_agent",
            name="Nexus-AlertAgent-v1",
            description="Monitors thresholds and sends real-time notifications",
            capabilities=["price_alerts", "sentiment_alerts", "whale_alerts"],
            price_per_query=0.0001,
            keywords=[
                "alert", "notify", "monitor", "threshold", "watch",
                "warn", "ping me", "tell me when", "let me know when",
            ],
            example_queries=[
                "Alert me when ETH drops 5%",
                "Monitor KITE price",
                "Notify on whale activity for SOL",
            ],
            # AlertAgent is independent; doesn't need other agent outputs.
            consumes=[],
            provides=["alert_status"],
        )
        self.active_rules: list[AlertRule] = []
        self._monitoring = False

    def prepare_request(self, capability: str, context: dict) -> dict:
        """AlertAgent works on the query directly; doesn't need previous outputs."""
        return {
            "type": "check_alerts",
            "capability": capability,
            "query": context.get("query", ""),
            "current_data": {},  # AlertAgent has its own rules to check
        }

    async def handle_request(self, request: dict) -> dict:
        """
        Handle alert-related requests.
        Types: create_alert, list_alerts, delete_alert, check_alerts
        """
        req_type = request.get("type", "create_alert")

        if req_type == "create_alert":
            return await self.create_alert(request)
        elif req_type == "list_alerts":
            return self.list_alerts()
        elif req_type == "delete_alert":
            return self.delete_alert(request.get("rule_id", ""))
        elif req_type == "check_alerts":
            return await self.check_all_alerts(request.get("current_data", {}))
        else:
            return {"error": f"Unknown request type: {req_type}"}

    async def create_alert(self, request: dict) -> dict:
        """Create a new alert monitoring rule"""
        import uuid
        rule = AlertRule(
            rule_id=str(uuid.uuid4())[:8],
            alert_type=request.get("alert_type", "price_drop"),
            token=request.get("token", "KITE"),
            threshold=request.get("threshold", 5.0),
            direction=request.get("direction", "below"),
        )
        self.active_rules.append(rule)

        await ws_manager.broadcast(NexusEvent(
            event_type=EventType.ALERT_CREATED,
            agent_id=self.name,
            data={
                "rule_id": rule.rule_id,
                "alert_type": rule.alert_type,
                "token": rule.token,
                "threshold": rule.threshold,
            },
            message=f"Alert created: {rule.alert_type} for {rule.token} (threshold: {rule.threshold})",
        ))

        return {
            "agent": self.name,
            "action": "alert_created",
            "rule_id": rule.rule_id,
            "alert_type": rule.alert_type,
            "token": rule.token,
            "threshold": rule.threshold,
            "active_alerts": len(self.active_rules),
        }

    def list_alerts(self) -> dict:
        """List all active alert rules"""
        return {
            "agent": self.name,
            "active_alerts": len(self.active_rules),
            "rules": [
                {
                    "rule_id": r.rule_id,
                    "alert_type": r.alert_type,
                    "token": r.token,
                    "threshold": r.threshold,
                    "direction": r.direction,
                    "triggered": r.triggered,
                    "created_at": r.created_at.isoformat(),
                }
                for r in self.active_rules
            ],
        }

    def delete_alert(self, rule_id: str) -> dict:
        """Delete an alert rule"""
        self.active_rules = [r for r in self.active_rules if r.rule_id != rule_id]
        return {"agent": self.name, "action": "alert_deleted", "rule_id": rule_id}

    async def check_all_alerts(self, current_data: dict) -> dict:
        """Check all active rules against current data"""
        start = await self.start_work("Checking alert conditions")

        triggered = []
        price_data = current_data.get("price", {})
        sentiment_data = current_data.get("sentiment", {})
        whale_data = current_data.get("whale", {})

        for rule in self.active_rules:
            if rule.triggered:
                continue

            is_triggered = False
            trigger_value = None

            if rule.alert_type == "price_drop" and price_data:
                change = price_data.get("change_24h_pct", 0)
                if change < -rule.threshold:
                    is_triggered = True
                    trigger_value = change

            elif rule.alert_type == "price_spike" and price_data:
                change = price_data.get("change_24h_pct", 0)
                if change > rule.threshold:
                    is_triggered = True
                    trigger_value = change

            elif rule.alert_type == "whale" and whale_data:
                large_txs = whale_data.get("large_buys", 0) + whale_data.get("large_sells", 0)
                if large_txs >= rule.threshold:
                    is_triggered = True
                    trigger_value = large_txs

            elif rule.alert_type == "sentiment_shift" and sentiment_data:
                score = abs(sentiment_data.get("average_score", 0))
                if score > rule.threshold / 100:
                    is_triggered = True
                    trigger_value = score

            if is_triggered:
                rule.triggered = True
                triggered.append({
                    "rule_id": rule.rule_id,
                    "alert_type": rule.alert_type,
                    "token": rule.token,
                    "threshold": rule.threshold,
                    "actual_value": trigger_value,
                })

                await ws_manager.broadcast(NexusEvent(
                    event_type=EventType.ALERT_TRIGGERED,
                    agent_id=self.name,
                    data={
                        "rule_id": rule.rule_id,
                        "alert_type": rule.alert_type,
                        "trigger_value": trigger_value,
                    },
                    message=f"ALERT: {rule.alert_type} for {rule.token}! Value: {trigger_value}",
                ))

            rule.last_checked = datetime.utcnow()

        duration = await self.complete_work(f"Checked {len(self.active_rules)} alerts, {len(triggered)} triggered", start)

        return {
            "agent": self.name,
            "rules_checked": len(self.active_rules),
            "alerts_triggered": triggered,
            "duration_ms": duration,
        }

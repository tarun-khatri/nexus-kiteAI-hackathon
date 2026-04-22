"""
NEXUS - WebSocket Connection Manager
Handles real-time event broadcasting to the dashboard.
Every agent action, payment, and audit result is pushed here.
"""

import json
import asyncio
from typing import Any
from fastapi import WebSocket
from datetime import datetime

from backend.models.events import NexusEvent, EventType


class ConnectionManager:
    """Manages WebSocket connections and broadcasts events to all connected dashboards"""

    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.event_history: list[dict] = []  # Store recent events for new connections
        self.max_history = 200  # Keep last 200 events

    async def connect(self, websocket: WebSocket):
        """Accept a new WebSocket connection from the dashboard"""
        await websocket.accept()
        self.active_connections.append(websocket)
        # Send recent event history to new connection
        if self.event_history:
            await websocket.send_json({
                "event": "history",
                "data": self.event_history[-50:],  # Last 50 events
            })

    def disconnect(self, websocket: WebSocket):
        """Remove a disconnected WebSocket"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, event: NexusEvent):
        """Send an event to ALL connected dashboards"""
        message = event.to_ws_message()

        # Store in memory history (ephemeral -- current session only).
        # On-chain payment history is restored from PaymentRouter contract
        # on startup, so economic events survive restarts via the chain.
        # Application-layer events (discovery, work_started, etc.) are
        # ephemeral by design -- they're real-time telemetry, not ledger data.
        self.event_history.append(message)
        if len(self.event_history) > self.max_history:
            self.event_history = self.event_history[-self.max_history:]

        # Broadcast to all connections
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)

        # Clean up dead connections
        for conn in disconnected:
            self.disconnect(conn)

    async def emit_agent_discovery(self, from_agent: str, found_agent: str, capability: str):
        """Emit when an agent discovers another agent"""
        await self.broadcast(NexusEvent(
            event_type=EventType.AGENT_DISCOVERY,
            agent_id=from_agent,
            target_agent_id=found_agent,
            data={"capability": capability},
            message=f"{from_agent} discovered {found_agent} for {capability}",
        ))

    async def emit_payment(self, from_agent: str, to_agent: str, amount: float, purpose: str, tx_hash: str = ""):
        """Emit when a payment is made between agents"""
        await self.broadcast(NexusEvent(
            event_type=EventType.PAYMENT_SENT,
            agent_id=from_agent,
            target_agent_id=to_agent,
            data={"amount": amount, "purpose": purpose, "tx_hash": tx_hash},
            message=f"{from_agent} paid ${amount:.4f} to {to_agent} for {purpose}",
        ))

    async def emit_work_started(self, agent_id: str, task: str):
        """Emit when an agent starts working"""
        await self.broadcast(NexusEvent(
            event_type=EventType.WORK_STARTED,
            agent_id=agent_id,
            data={"task": task},
            message=f"{agent_id} started: {task}",
        ))

    async def emit_work_completed(
        self, agent_id: str, task: str, duration_ms: float,
        tx_hash: str = "",
    ):
        """Emit when an agent finishes a task. `tx_hash` (optional) lets the
        UI render a clickable link to the corresponding on-chain tx when the
        work was tied to one (e.g. reputation write or audit trail write)."""
        data = {"task": task, "duration_ms": duration_ms}
        if tx_hash:
            data["tx_hash"] = tx_hash
        await self.broadcast(NexusEvent(
            event_type=EventType.WORK_COMPLETED,
            agent_id=agent_id,
            data=data,
            message=f"{agent_id} completed: {task} ({duration_ms:.0f}ms)",
        ))

    async def emit_audit_result(self, auditor: str, target: str, score: int, checks: list):
        """Emit when AuditAgent verifies another agent's output"""
        await self.broadcast(NexusEvent(
            event_type=EventType.AUDIT_COMPLETED,
            agent_id=auditor,
            target_agent_id=target,
            data={"quality_score": score, "checks": checks},
            message=f"{auditor} verified {target}: quality score {score}/100",
        ))

    async def emit_reputation_update(
        self, agent_id: str, old_score: int, new_score: int,
        tx_hash: str = "",
    ):
        """Emit when an agent's reputation changes on-chain. `tx_hash`
        (optional) carries the ReputationTracker write tx so the UI can
        link straight to Kitescan."""
        data = {"old_score": old_score, "new_score": new_score}
        if tx_hash:
            data["tx_hash"] = tx_hash
        await self.broadcast(NexusEvent(
            event_type=EventType.REPUTATION_UPDATE,
            agent_id=agent_id,
            data=data,
            message=f"{agent_id} reputation: {old_score} -> {new_score}",
        ))

    async def emit_report_completed(self, report_id: str, query: str, total_cost: float, time_ms: float, agents_count: int):
        """Emit when a full report is delivered"""
        await self.broadcast(NexusEvent(
            event_type=EventType.REPORT_COMPLETED,
            data={
                "report_id": report_id,
                "query": query,
                "total_cost": total_cost,
                "time_ms": time_ms,
                "agents_involved": agents_count,
            },
            message=f"Report delivered: '{query}' | Cost: ${total_cost:.4f} | Time: {time_ms:.0f}ms",
        ))

    async def emit_governance_enforced(self, agent_id: str, rule: str, action: str):
        """Emit when a governance rule blocks or modifies agent behavior"""
        await self.broadcast(NexusEvent(
            event_type=EventType.GOVERNANCE_RULE_ENFORCED,
            agent_id=agent_id,
            data={"rule": rule, "action": action},
            message=f"Governance enforced on {agent_id}: {rule} -> {action}",
        ))

    async def emit_system_info(self, message: str, data: dict = None):
        """Emit a system-level info message"""
        await self.broadcast(NexusEvent(
            event_type=EventType.SYSTEM_INFO,
            data=data or {},
            message=message,
        ))


# Global WebSocket manager instance
ws_manager = ConnectionManager()

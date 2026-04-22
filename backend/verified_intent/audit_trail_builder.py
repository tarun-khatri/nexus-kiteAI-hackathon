"""
NEXUS - Audit Trail Builder
Builds traceability hashes and records them on-chain.
Links: user query -> mandate -> agent actions -> payments -> final report.
"""

import hashlib
import json
import uuid
from datetime import datetime

from backend.models.audit_trail import AuditTrailEntry
from backend.models.mandate import Mandate


class AuditTrailBuilder:
    """Collects all actions during a query and builds the traceability hash."""

    def __init__(self):
        self.trails: list[AuditTrailEntry] = []

    def build_trail(self, mandate: Mandate, report_dict: dict) -> AuditTrailEntry:
        """
        Compute traceability hash from the full chain:
        query + mandate + payments + report
        """
        # Hash the final report
        report_json = json.dumps(report_dict, sort_keys=True, default=str)
        report_hash = hashlib.sha256(report_json.encode()).hexdigest()

        # Build the payments list from mandate's payment log
        payments = [
            {
                "to_agent": p.to_agent,
                "amount": p.amount,
                "purpose": p.purpose,
                "tx_hash": p.tx_hash,
            }
            for p in mandate.payment_log
        ]

        # Build agent actions from the report sections
        agent_actions = []
        sections = report_dict.get("sections", {})
        for section_name, section_data in sections.items():
            agent_actions.append({
                "agent": section_data.get("agent", "unknown"),
                "action": section_name,
                "timestamp": datetime.utcnow().isoformat(),
            })

        # Compute traceability hash
        trace_data = (
            mandate.query
            + mandate.model_dump_json()
            + json.dumps(payments, default=str)
            + report_hash
        )
        traceability_hash = hashlib.sha256(trace_data.encode()).hexdigest()

        trail = AuditTrailEntry(
            trail_id=f"trail-{uuid.uuid4().hex[:12]}",
            mandate_id=mandate.mandate_id,
            query=mandate.query,
            context_hash=mandate.context_hash,
            traceability_hash=traceability_hash,
            report_hash=report_hash,
            agent_actions=agent_actions,
            payments=payments,
        )

        self.trails.append(trail)
        print(f"[AuditTrail] Built trail {trail.trail_id}: hash={traceability_hash[:16]}...")
        return trail

    async def record_on_chain(self, trail: AuditTrailEntry) -> AuditTrailEntry:
        """
        Record the traceability hash on-chain via kite_client. Safe to call
        from a background task (asyncio.create_task) — emits a WebSocket
        event with the final tx_hash so dashboards can update.
        """
        from backend.blockchain.kite_client import kite_client
        from backend.websocket.manager import ws_manager
        from backend.models.events import NexusEvent, EventType

        try:
            tx_hash = await kite_client.log_audit_trail(
                trail.traceability_hash, trail.mandate_id
            )
        except Exception as e:
            print(f"[AuditTrail] on-chain record failed: {e}")
            tx_hash = None

        if tx_hash:
            trail.on_chain_tx_hash = tx_hash
            trail.explorer_url = kite_client.get_tx_explorer_url(tx_hash)
            print(f"[AuditTrail] Recorded on-chain: {trail.explorer_url}")

            # Emit the "recorded" WebSocket event so the UI can swap
            # "pending" for the explorer URL.
            try:
                await ws_manager.broadcast(NexusEvent(
                    event_type=EventType.AUDIT_TRAIL_RECORDED,
                    data={
                        "trail_id": trail.trail_id,
                        "mandate_id": trail.mandate_id,
                        "traceability_hash": trail.traceability_hash,
                        "on_chain_tx_hash": tx_hash,
                        "explorer_url": trail.explorer_url,
                        "chain_status": "recorded",
                    },
                    message=f"Audit trail recorded on-chain: {trail.explorer_url}",
                ))
            except Exception as e:
                print(f"[AuditTrail] ws broadcast failed: {e}")
        else:
            print("[AuditTrail] On-chain recording unavailable (local mode or RPC failure)")

        # Persist to SQLite
        try:
            from backend.db import save_audit_trail
            await save_audit_trail({
                "trail_id": trail.trail_id,
                "mandate_id": trail.mandate_id,
                "traceability_hash": trail.traceability_hash,
                "report_hash": trail.report_hash,
                "on_chain_tx_hash": trail.on_chain_tx_hash or "",
                "explorer_url": trail.explorer_url or "",
                "query": trail.query,
            })
        except Exception:
            pass  # DB persistence is best-effort

        return trail


# Global singleton
audit_trail_builder = AuditTrailBuilder()

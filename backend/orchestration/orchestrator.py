"""
NEXUS - Agent Orchestrator

Single entry point for invoking ANY agent (in-process built-in or external
marketplace). Enforces:

  1. Schema-validated input (via the capability's input_schema).
  2. Pre-flight health probe.
  3. Circuit-breaker-gated on-chain payment.
  4. Uniform envelope response (success OR failure — same shape).
  5. Structured mandate bookkeeping (SUCCEEDED / FAILED_DOWNSTREAM / BLOCKED_UNREACHABLE).
  6. WebSocket events at each step.

Downstream callers (ReportAgent) just hand us an InvocationRequest and get
back an InvocationResult. No branching on agent type or capability name.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from backend.orchestration.envelope import (
    InvocationRequest,
    InvocationResult,
    InvocationStatus,
    ErrorCode,
    wrap_legacy_result,
)
from backend.orchestration.identifier_extractor import validate_input
from backend.marketplace.probe import agent_prober
from backend.marketplace.capability_registry import CapabilitySpec
from backend.models.transaction import Transaction, TransactionStatus, TransactionType
from backend.models.events import NexusEvent, EventType
from backend.models.mandate import PaymentRecordStatus
from backend.websocket.manager import ws_manager


class Orchestrator:
    """
    Dispatcher for agent invocations. Stateless; uses module-level singletons
    for marketplace, mandate_manager, circuit_breaker, kite_client.
    """

    async def invoke(
        self,
        request: InvocationRequest,
        *,
        spec: CapabilitySpec,
        from_agent_name: str,
        from_agent_reputation: int = 50,
        builtin_agent: Optional[Any] = None,
        marketplace_agent: Optional[Any] = None,
    ) -> InvocationResult:
        """
        Run one capability invocation end-to-end.

        Exactly one of `builtin_agent` (Python BaseAgent subclass) OR
        `marketplace_agent` (ExternalAgent) must be provided.
        """
        t0 = time.time()
        tag = f"[Orch] {request.agent_name}/{request.capability}"
        result_base = {
            "request_id": request.request_id,
            "agent_id": request.agent_id,
            "agent_name": request.agent_name,
            "capability": request.capability,
            "source": "builtin" if builtin_agent is not None else "marketplace",
        }

        # --- 1. Validate input against the capability's input_schema ---
        if spec.input_schema:
            ok, err = validate_input(request.input, spec.input_schema)
            if not ok:
                print(f"{tag} INVALID_INPUT: {err}")
                return InvocationResult(
                    **result_base,
                    status=InvocationStatus.INVALID_INPUT,
                    error_code=ErrorCode.INVALID_INPUT,
                    error_message=err or "Input failed schema validation.",
                    duration_ms=round((time.time() - t0) * 1000, 1),
                )

        # --- 2. Pre-flight probe (marketplace only; built-ins always reachable) ---
        callback_url = None
        if marketplace_agent is not None:
            callback_url = marketplace_agent.callback_url

        probe_t0 = time.time()
        probe_result = await agent_prober.probe(request.agent_id, callback_url)
        print(f"{tag} probe: reachable={probe_result.reachable} ({(time.time()-probe_t0)*1000:.0f}ms)")
        if not probe_result.reachable:
            # Record as BLOCKED_UNREACHABLE in the mandate (no chain tx fires).
            await self._record_blocked_unreachable(
                from_agent_name, request, probe_result.error or "probe failed",
            )
            return InvocationResult(
                **result_base,
                status=InvocationStatus.UNREACHABLE,
                error_code=ErrorCode.UNREACHABLE,
                error_message=f"Probe failed: {probe_result.error or 'unreachable'}",
                error_hint="Agent may be down. Payment NOT executed.",
                duration_ms=round((time.time() - t0) * 1000, 1),
            )

        # --- 3. Execute on-chain payment via circuit breaker ---
        from backend.agents.base_agent import BaseAgent  # avoid circular import
        paying_agent = self._find_paying_agent(from_agent_name, builtin_agent)
        price = spec.price_usdc

        pay_t0 = time.time()
        print(f"{tag} paying ${price} (on-chain tx...)")
        payment_tx = await self._make_payment(
            paying_agent=paying_agent,
            from_agent_name=from_agent_name,
            to_agent_name=request.agent_name,
            amount=price,
            purpose=request.capability,
            mandate_id=request.mandate_id,
        )
        print(f"{tag} payment settled in {(time.time()-pay_t0)*1000:.0f}ms (status={payment_tx.status.value})")
        if payment_tx.status in (TransactionStatus.FAILED, TransactionStatus.BLOCKED_UNREACHABLE):
            return InvocationResult(
                **result_base,
                status=InvocationStatus.FAILED,
                error_code=ErrorCode.ORCHESTRATOR_ERROR,
                error_message=payment_tx.blocked_reason or "Circuit breaker rejected payment",
                duration_ms=round((time.time() - t0) * 1000, 1),
            )

        request.payment_tx_hash = payment_tx.tx_hash or payment_tx.tx_id
        result_base["payment_tx_hash"] = request.payment_tx_hash

        # --- 4. Invoke the agent ---
        print(f"{tag} invoking agent...")
        invoke_t0 = time.time()
        try:
            raw = await self._dispatch(
                request=request,
                builtin_agent=builtin_agent,
                marketplace_agent=marketplace_agent,
                from_agent_name=from_agent_name,
                payment_amount=price,
            )
        except TimeoutError as te:
            return await self._handle_downstream_failure(
                request=request,
                result_base=result_base,
                status=InvocationStatus.TIMEOUT,
                error_code=ErrorCode.TIMEOUT,
                error_message=str(te),
                t0=invoke_t0,
            )
        except Exception as e:
            return await self._handle_downstream_failure(
                request=request,
                result_base=result_base,
                status=InvocationStatus.FAILED,
                error_code=ErrorCode.ORCHESTRATOR_ERROR,
                error_message=f"Invocation raised: {type(e).__name__}: {e}",
                t0=invoke_t0,
            )

        print(f"{tag} agent returned in {(time.time()-invoke_t0)*1000:.0f}ms")

        # --- 5. Normalize to envelope ---
        envelope = wrap_legacy_result(
            raw,
            request=request,
            started_at=invoke_t0,
            source=result_base["source"],
            payment_tx_hash=request.payment_tx_hash,
        )
        print(f"{tag} DONE: status={envelope.status.value} total={(time.time()-t0)*1000:.0f}ms")

        if envelope.status != InvocationStatus.SUCCESS:
            # Mark mandate entry as FAILED_DOWNSTREAM (chain tx succeeded but agent errored).
            await self._record_failed_downstream(
                request=request,
                error_code=(envelope.error_code.value if envelope.error_code else ErrorCode.AGENT_ERROR.value),
                error_message=envelope.error_message,
            )

        # --- 6. Emit WS event (but avoid duplicating BaseAgent's own emit).
        # Built-in agents' `handle_request` already calls BaseAgent.complete_work()
        # on the success path, which broadcasts its own WORK_COMPLETED. If we
        # also broadcast here, the dashboard feed shows "done" twice. Skip
        # the duplicate for built-in success. Still emit for:
        #   • marketplace agents (they can't hook into BaseAgent in-process)
        #   • any non-success status (built-ins that failed before reaching
        #     complete_work() won't have emitted their own "done").
        should_emit = (
            result_base["source"] != "builtin"
            or not envelope.is_success()
        )
        if should_emit:
            await ws_manager.broadcast(NexusEvent(
                event_type=EventType.WORK_COMPLETED,
                agent_id=request.agent_name,
                data={
                    "capability": request.capability,
                    "status": envelope.status.value,
                    "duration_ms": envelope.duration_ms,
                    "error_code": envelope.error_code.value if envelope.error_code else None,
                    "error_message": envelope.error_message,
                },
                message=(
                    f"{request.agent_name} completed {request.capability} ({envelope.duration_ms:.0f}ms)"
                    if envelope.is_success()
                    else f"{request.agent_name} FAILED {request.capability}: {envelope.error_message}"
                ),
            ))

        return envelope

    # ---- helpers ----

    async def _dispatch(
        self,
        *,
        request: InvocationRequest,
        builtin_agent: Optional[Any],
        marketplace_agent: Optional[Any],
        from_agent_name: str,
        payment_amount: float,
    ):
        """Actually call the agent. Returns raw result (anything)."""
        if builtin_agent is not None:
            await builtin_agent.receive_payment(
                from_agent_name, payment_amount, request.capability,
            )
            legacy_request = builtin_agent.prepare_request(
                request.capability,
                {
                    "query": request.input.get("identifier") or request.input.get("query") or "",
                    "outputs": request.input.get("prior_outputs", {}),
                    "provides_index": request.input.get("provides_index", {}),
                    **request.input,  # pass through the structured input too
                },
            )
            return await builtin_agent.handle_request(legacy_request)

        if marketplace_agent is not None:
            from backend.marketplace.registry import marketplace
            # Pass both typed input AND legacy flattened keys so older agents keep working.
            payload = {
                "type": request.capability,
                "capability": request.capability,
                **request.input,
                "context": request.input.get("context", {}),
            }
            # `query` was the legacy single-field convention — preserve it so
            # existing agents that only read "query" still work. Prefer the
            # schema-extracted identifier when present.
            if "query" not in payload:
                payload["query"] = (
                    request.input.get("identifier")
                    or request.input.get("query")
                    or ""
                )
            return await marketplace.invoke_agent(request.agent_id, payload)

        return {"error": "No dispatcher target"}

    async def _make_payment(
        self,
        *,
        paying_agent: Optional[Any],
        from_agent_name: str,
        to_agent_name: str,
        amount: float,
        purpose: str,
        mandate_id: Optional[str],
    ) -> Transaction:
        """Execute payment via the paying agent's make_payment() so circuit breaker runs."""
        if paying_agent is None:
            # Last-resort path (rare): construct a CONFIRMED tx without chain write.
            # The orchestrator always receives a valid paying agent, but we defend.
            return Transaction(
                tx_id=str(uuid.uuid4()),
                from_agent=from_agent_name,
                to_agent=to_agent_name,
                amount=amount,
                tx_type=TransactionType.PAYMENT,
                status=TransactionStatus.CONFIRMED,
                purpose=purpose,
                mandate_id=mandate_id,
            )
        return await paying_agent.make_payment(
            to_agent_name, amount, purpose, mandate_id=mandate_id,
        )

    def _find_paying_agent(self, from_agent_name: str, builtin_agent: Optional[Any]):
        """Find the BaseAgent that should pay. Usually it's the ReportAgent."""
        # Prefer the explicitly-provided builtin for self-pay edge cases, but
        # ReportAgent is the normal payer — main.py wires it into globals.
        try:
            import backend.main as main_module
            paying = getattr(main_module, "report_agent", None)
            if paying is not None and paying.name == from_agent_name:
                return paying
        except Exception:
            pass
        return builtin_agent

    async def _record_blocked_unreachable(
        self, from_agent_name: str, request: InvocationRequest, reason: str,
    ):
        """
        Log a BLOCKED_UNREACHABLE payment record (no chain tx), emit a WS
        event so dashboards show the block, and notify the mandate tracker.
        """
        if request.mandate_id:
            try:
                from backend.verified_intent.mandate_manager import mandate_manager
                mandate_manager.record_payment(
                    request.mandate_id,
                    request.agent_name,
                    0.0,
                    request.capability,
                    tx_hash="",
                    status=PaymentRecordStatus.BLOCKED_UNREACHABLE,
                    error_code=ErrorCode.UNREACHABLE.value,
                    error_message=reason,
                )
            except Exception as e:
                print(f"[Orchestrator] mandate record BLOCKED_UNREACHABLE failed: {e}")

        await ws_manager.broadcast(NexusEvent(
            event_type=EventType.CIRCUIT_BREAKER_BLOCKED,
            agent_id=from_agent_name,
            target_agent_id=request.agent_name,
            data={
                "approved": False,
                "verdict": "blocked_unreachable",
                "to_agent": request.agent_name,
                "detail": f"Probe failed: {reason}",
                "mandate_id": request.mandate_id,
            },
            message=f"Probe blocked payment to {request.agent_name} ({reason})",
        ))

    async def _record_failed_downstream(
        self,
        *,
        request: InvocationRequest,
        error_code: str,
        error_message: Optional[str],
    ):
        """Flip the mandate's payment-log entry to FAILED_DOWNSTREAM."""
        if not request.mandate_id or not request.payment_tx_hash:
            return
        try:
            from backend.verified_intent.mandate_manager import mandate_manager
            mandate_manager.mark_payment_failed(
                request.mandate_id,
                request.payment_tx_hash,
                error_code=error_code,
                error_message=error_message,
            )
        except Exception as e:
            print(f"[Orchestrator] mandate mark_payment_failed error: {e}")

    async def _handle_downstream_failure(
        self,
        *,
        request: InvocationRequest,
        result_base: dict,
        status: InvocationStatus,
        error_code: ErrorCode,
        error_message: str,
        t0: float,
    ) -> InvocationResult:
        envelope = InvocationResult(
            **result_base,
            status=status,
            error_code=error_code,
            error_message=error_message,
            duration_ms=round((time.time() - t0) * 1000, 1),
        )
        await self._record_failed_downstream(
            request=request,
            error_code=error_code.value,
            error_message=error_message,
        )
        await ws_manager.broadcast(NexusEvent(
            event_type=EventType.WORK_COMPLETED,
            agent_id=request.agent_name,
            data={
                "capability": request.capability,
                "status": status.value,
                "error_code": error_code.value,
                "error_message": error_message,
            },
            message=f"{request.agent_name} FAILED: {error_message}",
        ))
        return envelope


# Global singleton
orchestrator = Orchestrator()

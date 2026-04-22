"""
NEXUS - ReportAgent (Dynamic, Envelope-Based Orchestrator)

Flow per query:
  1. Discover capabilities via the LLM router (capability_registry.names()).
  2. Optionally append author-declared enrichments (per-capability).
  3. Create a mandate (spending bound), ECDSA-signed.
  4. Topo-sort by declared provides/consumes.
  5. Dispatch every capability through orchestrator.invoke() — returns an
     InvocationResult envelope (success/failed/timeout/unreachable — uniform).
  6. Build report.sections[] with one envelope per capability, success or fail.
  7. LLM-compiled summary over whatever envelopes succeeded.
  8. Write audit trail on-chain, complete mandate, emit report_completed.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime
from typing import Any, Optional

from backend.agents.base_agent import BaseAgent
from backend.agents.data_agent import DataAgent
from backend.agents.analyst_agent import AnalystAgent
from backend.agents.audit_agent import AuditAgent
from backend.llm import llm_router
from backend.models.events import NexusEvent, EventType
from backend.websocket.manager import ws_manager
from backend.config import DEFAULT_GOVERNANCE

from backend.marketplace.capability_registry import capability_registry, CapabilitySpec
from backend.orchestration.envelope import (
    InvocationRequest, InvocationResult, InvocationStatus,
)
from backend.orchestration.orchestrator import orchestrator


class ReportAgent(BaseAgent):

    def __init__(self, data_agent: DataAgent, analyst_agent: AnalystAgent,
                 audit_agent: AuditAgent,
                 mandate_manager=None, circuit_breaker=None,
                 audit_trail_builder=None, identity_resolver=None):
        super().__init__(
            agent_id="report_agent",
            name="Nexus-ReportAgent-v1",
            description="Orchestrates other agents and compiles comprehensive reports",
            capabilities=["report_generation", "orchestration"],
            price_per_query=0.0005,
            keywords=["report", "summary", "compile", "orchestrate", "full analysis"],
            example_queries=[
                "Full report on SOL",
                "Compile analysis for KITE",
                "Give me everything on ETH",
            ],
            consumes=["raw_data", "analysis_output", "quality_score"],
            provides=["final_report"],
        )
        self.data_agent = data_agent
        self.analyst_agent = analyst_agent
        self.audit_agent = audit_agent

        self.mandate_manager = mandate_manager
        self.circuit_breaker = circuit_breaker
        self.audit_trail_builder = audit_trail_builder
        self.identity_resolver = identity_resolver

        self.governance = dict(DEFAULT_GOVERNANCE)

        # Local map of agent_id -> BaseAgent, used when dispatching built-ins.
        self._builtin_by_id: dict[str, BaseAgent] = {
            "data_agent": self.data_agent,
            "analyst_agent": self.analyst_agent,
            "audit_agent": self.audit_agent,
        }

    # ============================================================
    # Main entry point
    # ============================================================
    async def handle_request(self, request: dict) -> dict:
        query: str = request.get("query", "") or ""
        enrichments_pref: str = str(request.get("enrichments", "auto"))  # "auto" | "off" | list
        report_id = str(uuid.uuid4())[:12]

        total_start = time.time()

        await ws_manager.broadcast(NexusEvent(
            event_type=EventType.REPORT_STARTED,
            agent_id=self.name,
            data={"report_id": report_id, "query": query},
            message=f"Starting report: '{query}'",
        ))

        start = await self.start_work(f"Orchestrating report for: {query}")

        # --- 1. Classify via the capability-registry-driven discovery ---
        from backend.marketplace.discovery import discovery_engine
        classification = await discovery_engine.classify_query(
            query, user_enrichment_pref=enrichments_pref,
        )
        plan = discovery_engine.build_execution_plan(classification)

        # Human-readable discovery message for the live feed. Fields the
        # frontend can rely on: status, capabilities (list of strings),
        # agent_names (list of full agent names), missing_capabilities.
        selected_caps = [s.capability for s in classification.selections]
        selected_names = [s.agent_name for s in classification.selections]
        if classification.selections:
            _msg = (
                f"Routed to {len(classification.selections)} agent(s): "
                f"{', '.join(selected_caps)}"
            )
        elif classification.missing_capabilities:
            _msg = (
                f"No agent found for: "
                f"{', '.join(classification.missing_capabilities)}"
            )
        else:
            _msg = f"Discovery status: {classification.status}"

        await ws_manager.broadcast(NexusEvent(
            event_type=EventType.AGENT_DISCOVERY,
            agent_id=self.name,
            data={
                "status": classification.status,
                "capabilities": selected_caps,
                "agent_names": selected_names,
                "agents_selected": len(classification.selections),
                "missing_capabilities": classification.missing_capabilities,
                "plan": plan,
            },
            message=_msg,
        ))

        # --- 2. Terminal-state classifications ---
        if classification.status == "router_unavailable":
            await self.complete_work("Router unavailable", start)
            return {
                "status": "error",
                "error_code": "router_unavailable",
                "report_id": report_id,
                "query": query,
                "message": "The LLM router is currently unavailable. Please try again shortly.",
                "execution_plan": plan,
                "sections": {},
                "timestamp": datetime.utcnow().isoformat(),
            }

        if classification.status == "not_applicable":
            await self.complete_work("Query not in scope", start)
            return {
                "status": "error",
                "error_code": "not_in_scope",
                "report_id": report_id,
                "query": query,
                "message": "This query isn't in scope for any registered capability.",
                "reasoning": classification.reasoning,
                "execution_plan": plan,
                "sections": {},
                "timestamp": datetime.utcnow().isoformat(),
            }

        if classification.status == "no_agent_available" or not classification.selections:
            await self.complete_work("No agents available", start)
            return {
                "status": "error",
                "error_code": "no_agent_available",
                "report_id": report_id,
                "query": query,
                "missing_capabilities": classification.missing_capabilities,
                "message": "No registered capability covers this query yet.",
                "hint": "Register an agent at POST /api/marketplace/register, or click '+ Register Agent' in the UI.",
                "execution_plan": plan,
                "sections": {},
                "timestamp": datetime.utcnow().isoformat(),
            }

        # --- 3. Create the mandate ---
        mandate = None
        if self.mandate_manager:
            agent_prices = {s.agent_name: s.price for s in classification.selections}
            all_allowed = list({*agent_prices.keys(), self.name})
            mandate = self.mandate_manager.create_mandate(
                query=query,
                allowed_agents=all_allowed,
                agent_prices=agent_prices,
            )
            await ws_manager.broadcast(NexusEvent(
                event_type=EventType.MANDATE_CREATED,
                agent_id=self.name,
                data={
                    "mandate_id": mandate.mandate_id,
                    "total_budget": mandate.total_budget,
                    "max_per_tx": mandate.max_per_tx,
                    "expires_at": mandate.expires_at.isoformat(),
                    "context_hash": mandate.context_hash,
                    "allowed_agents": mandate.allowed_agents,
                    "signature": mandate.signature[:20] + "..." if len(mandate.signature) > 20 else mandate.signature,
                    "signer": mandate.signer_address,
                },
                message=f"Mandate created: {mandate.mandate_id} | Budget: ${mandate.total_budget:.4f}",
            ))
        mandate_id = mandate.mandate_id if mandate else None

        # --- 4. Topo-sort selections + execute via orchestrator ---
        ordered_selections = self._topological_sort(classification.selections)
        envelopes: list[InvocationResult] = []
        prior_outputs: dict[str, dict] = {}  # capability -> output dict

        for sel in ordered_selections:
            spec: CapabilitySpec = sel.provider

            # Build typed input for the agent:
            #   - schema-extracted identifiers (from classify_query)
            #   - original raw query (for agents that still want free-form text)
            #   - prior_outputs so consumers see what producers produced
            input_payload: dict[str, Any] = {
                **sel.identifiers,
                "query": query,
                "prior_outputs": prior_outputs,
                "context": {
                    "capability": sel.capability,
                    "identifiers": sel.identifiers,
                    "prior_outputs": prior_outputs,
                },
            }

            # Find the live agent object (built-in Python or marketplace record).
            builtin_agent = self._builtin_by_id.get(sel.agent_id)
            marketplace_agent = None
            if builtin_agent is None:
                from backend.marketplace.registry import marketplace
                marketplace_agent = marketplace.external_agents.get(sel.agent_id)

            # Safety: no dispatch target? Record as FAILED envelope and continue.
            if builtin_agent is None and marketplace_agent is None:
                envelopes.append(InvocationResult(
                    request_id=uuid.uuid4().hex[:16],
                    agent_id=sel.agent_id,
                    agent_name=sel.agent_name,
                    capability=sel.capability,
                    status=InvocationStatus.FAILED,
                    error_message=f"No dispatch target for agent_id={sel.agent_id}",
                    source=sel.source,
                ))
                continue

            req = InvocationRequest(
                mandate_id=mandate_id,
                agent_id=sel.agent_id,
                agent_name=sel.agent_name,
                capability=sel.capability,
                input=input_payload,
                timeout_ms=spec.timeout_ms,
            )

            envelope = await orchestrator.invoke(
                req,
                spec=spec,
                from_agent_name=self.name,
                from_agent_reputation=self.reputation_score,
                builtin_agent=builtin_agent,
                marketplace_agent=marketplace_agent,
            )
            envelopes.append(envelope)

            if envelope.is_success() and envelope.output:
                prior_outputs[sel.capability] = envelope.output

        # --- 5. Reputation updates (policy: audit-score-driven) ---
        # Fire-and-forget: on-chain reputation writes each take 20-30s on Kite
        # testnet. Blocking the response on them kills UX. The reputation will
        # be visible in the next /api/reputation poll (5s cache TTL), which is
        # acceptable latency — the report response already includes the
        # payment-tx hash and envelope status so the user sees the outcome.
        audit_output = self._extract_audit_output(envelopes)
        quality_score = int(audit_output.get("quality_score", 0)) if audit_output else 0
        asyncio.create_task(self._update_reputations(envelopes, quality_score))
        print(f"[Report] scheduled reputation updates for {len(envelopes)} envelope(s) (background)")

        # (Alert check removed — AlertAgent is deregistered. Notifications
        # aren't deliverable without a real notification channel; the
        # capability will return when that's implemented.)

        # --- 7. Compile the final report ---
        total_cost = sum(e.payment_tx_hash and e.is_success() and classification_price(e, classification)
                         or 0.0 for e in envelopes)
        # Re-compute total_cost from selections (cleaner)
        total_cost = sum(
            sel.price for sel, env in zip(ordered_selections, envelopes)
            if env.is_success()
        )
        total_time_ms = (time.time() - total_start) * 1000

        report = await self._compile_report(
            report_id=report_id,
            query=query,
            classification=classification,
            envelopes=envelopes,
            ordered_selections=ordered_selections,
            audit_output=audit_output,
            total_cost_usdc=total_cost,
            total_time_ms=total_time_ms,
        )
        report["execution_plan"] = plan

        # --- 8. Audit trail + mandate completion ---
        # Local hash + signature: synchronous (cheap, needed in response).
        # On-chain tx: fire-and-forget (takes 20-30s on Kite testnet; the
        # tx_hash is pushed via WebSocket once it lands).
        if mandate and self.audit_trail_builder:
            try:
                trail = self.audit_trail_builder.build_trail(mandate, report)
                # Kick off the chain write in the background; callers polling
                # /api/audit-trail will see the tx hash after it lands.
                asyncio.create_task(self.audit_trail_builder.record_on_chain(trail))
                print(f"[Report] scheduled audit-trail chain record for {trail.trail_id} (background)")

                report["verified_intent"] = {
                    "mandate_id": mandate.mandate_id,
                    "context_hash": mandate.context_hash,
                    "total_budget": mandate.total_budget,
                    "total_spent": round(mandate.cumulative_spent, 6),
                    "budget_remaining": round(mandate.budget_remaining, 6),
                    "max_per_tx": mandate.max_per_tx,
                    "signature": mandate.signature,
                    "signer": mandate.signer_address,
                    "status": mandate.status.value,
                    "expires_at": mandate.expires_at.isoformat(),
                    "payments": len(mandate.payment_log),
                    "payment_log": [p.model_dump(mode="json") for p in mandate.payment_log],
                }
                report["audit_trail"] = {
                    "trail_id": trail.trail_id,
                    "traceability_hash": trail.traceability_hash,
                    "report_hash": trail.report_hash,
                    # Tx hash is filled in async; may be None in the first response.
                    "on_chain_tx_hash": trail.on_chain_tx_hash,
                    "explorer_url": trail.explorer_url,
                    "chain_status": "pending" if not trail.on_chain_tx_hash else "recorded",
                }
                # Emit a "pending" audit-trail event so the activity feed
                # shows the trail ID immediately; a second "recorded" event
                # fires when the background chain write completes.
                await ws_manager.broadcast(NexusEvent(
                    event_type=EventType.AUDIT_TRAIL_RECORDED,
                    agent_id=self.name,
                    data={
                        "trail_id": trail.trail_id,
                        "mandate_id": mandate.mandate_id,
                        "traceability_hash": trail.traceability_hash,
                        "on_chain_tx_hash": None,
                        "explorer_url": None,
                        "chain_status": "pending",
                    },
                    message=f"Audit trail built: {trail.traceability_hash[:16]}... (chain write in progress)",
                ))

                # Complete mandate BEFORE returning so /api/mandates agrees
                # with the `status` field the caller sees in this response.
                self.mandate_manager.complete_mandate(mandate.mandate_id)
                # Refresh the dict we embedded with the post-completion status.
                report["verified_intent"]["status"] = mandate.status.value

                await ws_manager.broadcast(NexusEvent(
                    event_type=EventType.MANDATE_COMPLETED,
                    agent_id=self.name,
                    data={
                        "mandate_id": mandate.mandate_id,
                        "total_spent": round(mandate.cumulative_spent, 6),
                        "total_budget": mandate.total_budget,
                    },
                    message=f"Mandate completed: {mandate.mandate_id}",
                ))
            except Exception as e:
                print(f"[Report] audit-trail/mandate finalize warning: {e}")

        await self.complete_work(f"Report completed for '{query}'", start)
        await ws_manager.emit_report_completed(
            report_id, query, total_cost, total_time_ms, len(envelopes),
        )

        return report

    # ============================================================
    # Reputation update policy
    # ============================================================
    async def _update_reputations(
        self, envelopes: list[InvocationResult], quality_score: int,
    ):
        """
        Policy: agents whose envelope was SUCCESS get rep+ based on audit score;
        agents whose envelope was FAILED/TIMEOUT/UNREACHABLE get rep- (-2).

        Works uniformly for built-in and marketplace agents — the orchestrator
        already wrote SUCCESS/FAILED_DOWNSTREAM into the mandate. Here we mirror
        that into the reputation contract so the chain reflects the outcome.
        """
        for env in envelopes:
            # Built-in: use BaseAgent.update_reputation (writes to chain + SQLite).
            builtin = self._builtin_by_id.get(env.agent_id)
            if builtin is not None:
                if env.is_success():
                    # Reputation deltas on SUCCESS are strictly additive.
                    #
                    # A successful envelope means the agent did its job — it
                    # produced output the orchestrator accepted. A low audit
                    # score in that case reflects a weak INPUT (e.g. off-topic
                    # query that starves the analysis), not agent failure.
                    # Penalizing the agent for user-input quality led to
                    # unfair negative drift (AuditAgent penalizing itself for
                    # honestly rating a non-crypto query as low-quality).
                    if quality_score >= 90:
                        await builtin.update_reputation(2, f"Audit score: {quality_score}")
                    elif quality_score >= 70:
                        await builtin.update_reputation(1, f"Audit score: {quality_score}")
                    # else: quality < 70 on a successful envelope → no delta.
                else:
                    # Envelope failed outright (timeout, unreachable, invalid
                    # input, agent error). That IS agent fault → penalty.
                    await builtin.update_reputation(
                        -2, f"Invocation {env.status.value}: {env.error_message or env.error_code}",
                    )
                continue

            # Marketplace: update the in-memory ExternalAgent record IMMEDIATELY
            # so /api/reputation + /api/agents reflect the change on the next
            # poll (the 60s catalog refresh isn't a bottleneck anymore).
            # THEN fire the on-chain write; it reconciles the canonical source.
            try:
                from backend.marketplace.registry import marketplace
                from backend.blockchain.kite_client import kite_client
                from backend.agent_catalog import agent_catalog
                from backend.db import save_marketplace_agent

                # Update ALL records matching this agent name — in older
                # deployments, duplicates could have accumulated in memory;
                # keep all of them in sync so whichever one the catalog
                # picks up, it sees the same fresh reputation.
                matching = [
                    e_obj for e_obj in marketplace.external_agents.values()
                    if e_obj.name == env.agent_name
                ]

                if env.is_success():
                    effective = quality_score if quality_score > 0 else 80
                    delta = 2 if effective >= 90 else (1 if effective >= 70 else 0)
                    for ext in matching:
                        ext.reputation_score = min(100, ext.reputation_score + delta)
                        ext.total_jobs += 1
                    agent_catalog._chain_cache_at = 0
                    # On-chain reputation write (serialized via kite_client lock).
                    await kite_client.record_success(env.agent_name, effective)
                else:
                    for ext in matching:
                        ext.reputation_score = max(0, ext.reputation_score - 5)
                        ext.total_jobs += 1
                    agent_catalog._chain_cache_at = 0
                    await kite_client.record_failure(env.agent_name)

                # Persist updated state to SQLite so it survives restarts.
                # Without this, the in-memory ext.reputation_score bump is lost
                # and a fresh boot shows everyone at rep=50 again.
                for ext in matching:
                    try:
                        await save_marketplace_agent({
                            "agent_id": ext.agent_id,
                            "name": ext.name,
                            "description": ext.description,
                            "capabilities": list(ext.capabilities),
                            "keywords": list(ext.keywords or []),
                            "example_queries": list(ext.example_queries or []),
                            "price_per_query": ext.price_per_query,
                            "callback_url": ext.callback_url,
                            "owner_address": ext.owner_address,
                            "passport_id": ext.passport_id,
                            "reputation_score": ext.reputation_score,
                            "total_jobs": ext.total_jobs,
                            "active": ext.active,
                            "registered_at": ext.registered_at.isoformat() if ext.registered_at else None,
                            "last_invoked": ext.last_invoked.isoformat() if ext.last_invoked else None,
                        })
                    except Exception:
                        pass  # persistence is best-effort
            except Exception as e:
                print(f"[Report] marketplace rep update warning: {e}")

    # ============================================================
    # Envelope helpers
    # ============================================================
    def _extract_audit_output(self, envelopes: list[InvocationResult]) -> dict:
        """Find the audit envelope (by capability name) and return its output."""
        for env in envelopes:
            if not env.is_success() or not env.output:
                continue
            # Accept any capability that yielded a quality_score/check structure.
            if "quality_score" in env.output or "checks" in env.output:
                return env.output
        # Fallback: explicit 'quality_audit' capability envelope (even if output-shape differs)
        for env in envelopes:
            if env.capability == "quality_audit" and env.is_success() and env.output:
                return env.output
        return {}

    def _extract_analysis_output(self, envelopes: list[InvocationResult]) -> Optional[dict]:
        """Find any analysis-type envelope's output for the alert checker."""
        for env in envelopes:
            if not env.is_success() or not env.output:
                continue
            if "analysis" in env.output:
                return env.output["analysis"]
        return None

    def _topological_sort(self, selections: list) -> list:
        """Order so producers run before consumers, based on declared provides/consumes.

        For built-ins, provides/consumes come from the agent instance. For
        marketplace agents, we default to producer-only (no consumes) unless
        their capability_spec declared otherwise. This keeps legacy agents
        working while letting new ones express deps explicitly.
        """
        def get_meta(sel) -> tuple[list[str], list[str]]:
            builtin = self._builtin_by_id.get(sel.agent_id)
            if builtin is not None:
                return (
                    list(getattr(builtin, "provides", builtin.capabilities)),
                    list(getattr(builtin, "consumes", [])),
                )
            # Marketplace: look at the capability_spec's output_schema keys as `provides`.
            provides = [sel.capability]
            consumes: list[str] = []
            return provides, consumes

        provides_index: dict[str, list] = {}
        meta_cache: dict[int, tuple[list[str], list[str]]] = {}
        for sel in selections:
            prov, cons = get_meta(sel)
            meta_cache[id(sel)] = (prov, cons)
            for p in prov:
                provides_index.setdefault(p, []).append(sel)

        in_degree = {id(s): 0 for s in selections}
        successors: dict[int, list] = {id(s): [] for s in selections}
        for sel in selections:
            _, cons = meta_cache[id(sel)]
            for needed in cons:
                for producer in provides_index.get(needed, []):
                    if producer is sel:
                        continue
                    successors[id(producer)].append(sel)
                    in_degree[id(sel)] += 1

        sorted_list: list = []
        ready = [s for s in selections if in_degree[id(s)] == 0]
        while ready:
            sel = ready.pop(0)
            sorted_list.append(sel)
            for nxt in successors[id(sel)]:
                in_degree[id(nxt)] -= 1
                if in_degree[id(nxt)] == 0:
                    ready.append(nxt)

        if len(sorted_list) < len(selections):
            seen = {id(s) for s in sorted_list}
            for s in selections:
                if id(s) not in seen:
                    sorted_list.append(s)
        return sorted_list

    # ============================================================
    # Dynamic report compiler (schema-agnostic)
    # ============================================================
    async def _compile_report(
        self,
        *,
        report_id: str,
        query: str,
        classification,
        envelopes: list[InvocationResult],
        ordered_selections: list,
        audit_output: dict,
        total_cost_usdc: float,
        total_time_ms: float,
    ) -> dict:
        """
        Build a report entirely from envelope data. No hardcoded fields.
        `output_fields` contains whatever keys appeared in any successful
        envelope's output — the UI renders what exists, nothing more.
        """
        import json as _json

        # One section per invoked capability, success or fail.
        sections: dict[str, dict] = {}
        for sel, env in zip(ordered_selections, envelopes):
            sections[sel.capability] = {
                **env.model_dump_for_report(),
                "provider_agent_id": sel.agent_id,
                "provider_source": sel.source,
                "provider_price_usdc": sel.price,
            }

        # Aggregate unique output fields across successful envelopes for frontend.
        output_fields: dict[str, Any] = {}
        for env in envelopes:
            if not env.is_success() or not env.output:
                continue
            for k, v in env.output.items():
                if k in ("agent", "query", "chain", "timestamp"):
                    continue
                if k not in output_fields:
                    output_fields[k] = v

        # Per-transaction summary (for the activity feed).
        transactions = []
        for sel, env in zip(ordered_selections, envelopes):
            transactions.append({
                "from": self.name,
                "to": sel.agent_name,
                "amount": sel.price,
                "purpose": sel.capability,
                "source": sel.source,
                "status": env.status.value,
                "tx_hash": env.payment_tx_hash,
            })

        # LLM summary over whatever succeeded.
        successful_outputs = {
            sel.capability: _truncate(env.output, max_items=3)
            for sel, env in zip(ordered_selections, envelopes)
            if env.is_success() and env.output
        }
        failed_capabilities = [
            {"capability": sel.capability, "agent": sel.agent_name, "error": env.error_message}
            for sel, env in zip(ordered_selections, envelopes)
            if not env.is_success()
        ]

        outputs_json = _json.dumps(successful_outputs, indent=1, default=str)[:3000]
        quality_txt = audit_output.get("quality_score", "N/A") if audit_output else "N/A"
        failed_note = (
            f"\n\nNote: {len(failed_capabilities)} capability(ies) failed to produce data: "
            + ", ".join(f"{f['capability']} ({f['error']})" for f in failed_capabilities)
        ) if failed_capabilities else ""

        summary_prompt = (
            f'You are summarizing a NEXUS agent-economy report.\n'
            f'Query: "{query}"\n\n'
            f'Successful agent outputs:\n{outputs_json}{failed_note}\n\n'
            f'Audit quality score: {quality_txt}/100\n\n'
            f'Write 3-4 concise, factual sentences. Include specific numbers where present. '
            f'If some capabilities failed, note that truthfully rather than hiding it. No markdown.'
        )
        try:
            summary = await llm_router.generate(
                prompt=summary_prompt,
                system_prompt="You are a professional crypto analyst. Be concise and honest.",
                max_tokens=280,
            )
        except Exception:
            summary = f"Compiled report for '{query}' with {len(successful_outputs)} successful agent(s)."

        return {
            "report_id": report_id,
            "query": query,
            "status": "ok" if successful_outputs else "partial",
            "summary": summary,
            "classification": {
                "status": classification.status,
                "requested_capabilities": classification.requested_capabilities,
                "missing_capabilities": classification.missing_capabilities,
                "reasoning": classification.reasoning,
            },
            "sections": sections,
            "output_fields": output_fields,
            "economy_stats": {
                "total_cost_usdc": round(total_cost_usdc, 6),
                "total_time_ms": round(total_time_ms, 1),
                "agents_involved": sum(1 for e in envelopes if e.is_success()),
                "agents_failed": sum(1 for e in envelopes if not e.is_success()),
                "transactions": transactions,
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

    def update_governance(self, rules: dict):
        self.governance.update(rules)


# ------- helpers at module level -------

def classification_price(env: InvocationResult, classification) -> float:
    """Recover the price for an envelope from the classification selections."""
    for s in classification.selections:
        if s.agent_id == env.agent_id and s.capability == env.capability:
            return s.price
    return 0.0


def _truncate(obj: Any, max_items: int = 5):
    """Trim large lists/dicts for LLM context."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(v, list) and len(v) > max_items:
                out[k] = v[:max_items]
                out[f"_{k}_total"] = len(v)
            elif isinstance(v, dict):
                out[k] = _truncate(v, max_items)
            else:
                out[k] = v
        return out
    return obj

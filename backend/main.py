"""
NEXUS - Main FastAPI Application
The Living Agent Economy on Kite Chain

This is the entry point for the backend server.
It initializes built-in agents, sets up API endpoints, and manages WebSocket connections.

Run: uvicorn backend.main:app --reload --port 8000
"""

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from backend.config import settings, AGENTS_CONFIG
from backend.marketplace.registry import marketplace
from backend.agents.data_agent import DataAgent
from backend.agents.analyst_agent import AnalystAgent
from backend.agents.report_agent import ReportAgent
from backend.agents.audit_agent import AuditAgent
# AlertAgent is intentionally NOT imported/registered: its capabilities promise
# external notifications (alerts, push, SMS) that the current infrastructure
# can't deliver. The code lives in backend/agents/alert_agent.py for future
# work; when real notification delivery is implemented, re-register it here.
from backend.websocket.manager import ws_manager
from backend.llm import llm_router
from backend.blockchain.kite_client import kite_client
from backend.verified_intent.mandate_manager import mandate_manager
from backend.verified_intent.circuit_breaker import CircuitBreaker
from backend.verified_intent.audit_trail_builder import audit_trail_builder
from backend.verified_intent.agent_identity_resolver import agent_identity_resolver

# Circuit breaker needs mandate_manager reference
circuit_breaker = CircuitBreaker(mandate_manager)


# ============================================================
# Initialize built-in agents
# ============================================================
data_agent = DataAgent()
analyst_agent = AnalystAgent()
audit_agent = AuditAgent()
report_agent = ReportAgent(
    data_agent, analyst_agent, audit_agent,
    mandate_manager=mandate_manager,
    circuit_breaker=circuit_breaker,
    audit_trail_builder=audit_trail_builder,
    identity_resolver=agent_identity_resolver,
)

ALL_AGENTS = [data_agent, analyst_agent, report_agent, audit_agent]


# ============================================================
# App lifecycle
# ============================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    # Startup
    print("=" * 60)
    print("  NEXUS - The Living Agent Economy on Kite Chain")
    print("=" * 60)
    print()

    # === Step 0: Initialize Database ===
    from backend.db import init_db
    await init_db()

    # === Step 1: Initialize LLM ===
    await llm_router.initialize()
    providers = llm_router.available_providers
    print(f"[LLM] Available providers: {', '.join(providers) if providers else 'NONE - configure .env!'}")

    # === Step 2: Connect to Kite Testnet ===
    print()
    connected = await kite_client.connect()
    if connected and kite_client.contracts_deployed:
        print("[Kite] All contracts loaded - REAL on-chain mode")

        # Register agents on-chain (or load existing if already registered)
        for agent in ALL_AGENTS:
            passport_id = kite_client._get_passport_id(agent.name).hex()
            agent.passport_id = passport_id
            agent.wallet_address = kite_client.account.address

            # Try to register (will fail silently if already registered)
            tx = await kite_client.register_agent(
                agent.name, agent.description, agent.capabilities, agent.price_per_query
            )
            if tx:
                print(f"[Agent] {agent.name} registered on-chain: {tx[:16]}...")
                await kite_client.init_reputation(agent.name)
            else:
                # Already registered - that's fine, just load existing
                print(f"[Agent] {agent.name} loaded (already on-chain) | passport: {passport_id[:16]}...")

        # Fund ReportAgent so it can pay other agents
        print("\n[Kite] Funding ReportAgent for x402 payments...")
        await kite_client.fund_agent(report_agent.name, 0.1)

        print(f"\n[Kite] Blockchain explorer: https://testnet.kitescan.ai/")
        print(f"[Kite] Total on-chain transactions: {len(kite_client.tx_hashes)}")
    elif connected:
        print("[Kite] Connected but contracts not deployed yet.")
        print("[Kite] Deploy contracts first: cd contracts && npx hardhat run deploy/deploy.js --network kiteTestnet")
        print("[Kite] Then add contract addresses to .env and restart.")
        for agent in ALL_AGENTS:
            print(f"[Agent] Registered (off-chain): {agent.name}")
    else:
        print("[Kite] Not connected to testnet - running in local mode")
        for agent in ALL_AGENTS:
            print(f"[Agent] Registered (local): {agent.name}")

    # === Step 3: Initialize Verified Intent System ===
    print()
    vi_signing = "ENABLED (ECDSA)" if settings.deployer_private_key else "DISABLED"
    vi_audit = "ON-CHAIN" if connected else "LOCAL"
    print(f"[VerifiedIntent] Mandate signing: {vi_signing}")
    print(f"[VerifiedIntent] Circuit breaker: ACTIVE")
    print(f"[VerifiedIntent] Audit trail: {vi_audit}")

    # === Step 4: Derive Agent Wallets ===
    from backend.blockchain.agent_wallets import agent_wallet_manager
    if kite_client.account:
        agent_wallet_manager.initialize(kite_client.account.address)
        for agent in ALL_AGENTS:
            if agent.passport_id:
                wallet = agent_wallet_manager.derive_wallet(agent.name, agent.passport_id)
                agent.wallet_address = wallet["address"]
        print(f"[Wallets] {len(agent_wallet_manager.wallets)} agent wallets derived")

    # Register built-in agents with the discovery engine so their self-declared
    # keywords and capabilities participate in the dynamic routing catalog.
    from backend.marketplace.discovery import register_builtin_agents
    register_builtin_agents({
        "data_agent": data_agent,
        "analyst_agent": analyst_agent,
        "audit_agent": audit_agent,
        "report_agent": report_agent,
    })
    print(f"[Discovery] Dynamic agent discovery: ACTIVE ({len(ALL_AGENTS)} built-in(s) self-registered)")
    print(f"[Marketplace] Open agent marketplace: ACTIVE")

    # === Step 5: REHYDRATE STATE from on-chain + SQLite ===
    # This is what makes restarts non-destructive. Reputation/earnings/marketplace
    # registrations survive because we pull them back from Kite chain + local DB.
    from backend.db import (
        load_agent_totals, load_agent_transactions, load_reputation_history,
        load_marketplace_agents,
    )
    from backend.models.transaction import Transaction, TransactionType, TransactionStatus

    def _status_from_str(s: str):
        s = (s or "").lower()
        if s == "confirmed":
            return TransactionStatus.CONFIRMED
        if s == "failed":
            return TransactionStatus.FAILED
        if s == "pending":
            return TransactionStatus.PENDING
        return TransactionStatus.CONFIRMED

    print("\n[Rehydrate] Restoring agent state from on-chain + SQLite...")
    for agent in ALL_AGENTS:
        # 1. Read authoritative reputation from ReputationTracker contract
        onchain_rep = None
        if connected and kite_client.contracts_deployed:
            try:
                onchain_rep = await kite_client.get_reputation(agent.name)
            except Exception:
                onchain_rep = None
        if onchain_rep is not None:
            agent.reputation_score = int(onchain_rep)

        # 2. Restore totals (earned/spent/jobs) from saved transactions
        totals = await load_agent_totals(agent.name)
        agent.total_earned = totals["total_earned"]
        agent.total_spent = totals["total_spent"]
        agent.total_jobs_completed = totals["total_jobs"]

        # 3. Restore transaction history (last 100)
        tx_rows = await load_agent_transactions(agent.name, limit=100)
        restored_txs = []
        for t in tx_rows:
            try:
                restored_txs.append(Transaction(
                    tx_id=t.get("tx_id") or "",
                    tx_hash=t.get("tx_hash") or None,
                    from_agent=t.get("from_agent") or "",
                    to_agent=t.get("to_agent") or "",
                    amount=t.get("amount") or 0,
                    tx_type=TransactionType.PAYMENT,
                    status=_status_from_str(t.get("status", "")),
                    purpose=t.get("purpose") or "",
                    mandate_id=t.get("mandate_id") or None,
                ))
            except Exception:
                continue
        # Oldest first for chronological display
        agent.transactions = list(reversed(restored_txs))

        # 4. Restore reputation change history
        rep_hist = await load_reputation_history(agent.name, limit=100)
        if rep_hist:
            agent.reputation_history = rep_hist

        print(f"[Rehydrate] {agent.name}: rep={agent.reputation_score} earned=${agent.total_earned:.4f} spent=${agent.total_spent:.4f} jobs={agent.total_jobs_completed} tx_restored={len(agent.transactions)}")

    # 5. Rehydrate marketplace external agents
    persisted_market = await load_marketplace_agents()
    if persisted_market:
        restored = marketplace.hydrate_from_persisted(persisted_market)
        print(f"[Rehydrate] Marketplace: restored {restored} external agent(s) from SQLite")
    else:
        print(f"[Rehydrate] Marketplace: no persisted agents found (fresh install)")

    # === Step 6: UNIFIED AGENT CATALOG ===
    # The catalog is the single source of truth for "all agents" across the
    # system (in-process + http-callback + on-chain-only). Frontend / API /
    # discovery all read from here. No more split between built-in and external.
    from backend.agent_catalog import agent_catalog
    agent_catalog.register_in_process_agents({
        "data_agent": data_agent,
        "analyst_agent": analyst_agent,
        "audit_agent": audit_agent,
        "report_agent": report_agent,
    })
    # Populate the chain cache once at startup (warms the cache).
    await agent_catalog.refresh_from_chain()
    catalog_agents = await agent_catalog.get_all()
    print(f"[Catalog] Unified agent catalog: {len(catalog_agents)} total agent(s)")
    by_source = {}
    for a in catalog_agents:
        by_source[a["source_type"]] = by_source.get(a["source_type"], 0) + 1
    print(f"[Catalog] Source breakdown: {by_source}")

    # Background sync task: every 60s, refresh the unified catalog from chain
    # AND refresh the economy snapshot cache used by /api/stats. Neither is
    # on the critical path of any HTTP request.
    async def _periodic_chain_sync():
        from backend.blockchain.chain_reader import chain_reader
        # Prime the economy-snapshot cache immediately so /api/stats has real
        # on-chain data from the first poll.
        try:
            await chain_reader.refresh_economy_snapshot()
            print(f"[Catalog] economy snapshot cache primed")
        except Exception as e:
            print(f"[Catalog] initial snapshot prime failed: {e}")

        while True:
            await asyncio.sleep(60)
            try:
                await agent_catalog.refresh_from_chain()
            except Exception as e:
                print(f"[Catalog] periodic sync failed: {e}")
            try:
                await chain_reader.refresh_economy_snapshot()
            except Exception as e:
                print(f"[Catalog] economy snapshot refresh failed: {e}")

    sync_task = asyncio.create_task(_periodic_chain_sync())
    app.state.catalog_sync_task = sync_task
    print(f"[Catalog] Periodic chain sync: ACTIVE (60s interval, snapshot cache)")

    # === Step 7: Live feed starts empty ===
    # Historical on-chain payments are NOT dumped into the live WebSocket
    # feed anymore — they would interleave with current-session events under
    # different timestamps and confuse users. Instead they are served on
    # demand via GET /api/onchain-history, which the frontend renders in a
    # dedicated "On-chain History" tab.
    print("[Events] Live feed starts empty. Historical payments available at /api/onchain-history")

    # Pre-warm price cache for common tokens (prevents timeouts during queries)
    print("[Cache] Pre-warming price data...")
    for token in ["KITE", "BTC", "ETH"]:
        try:
            await data_agent.coingecko.get_current_price(token)
            await data_agent.coingecko.get_historical_prices(token, 30)
        except Exception:
            pass
    print("[Cache] Price cache warmed")

    print()
    print(f"[Server] Backend running on http://localhost:{settings.backend_port}")
    print(f"[Server] Dashboard URL: {settings.frontend_url}")
    print(f"[Server] WebSocket: ws://localhost:{settings.backend_port}/ws")
    if connected:
        print(f"[Server] Block Explorer: https://testnet.kitescan.ai/")
    print()

    await ws_manager.emit_system_info("Nexus economy initialized", {
        "agents": len(ALL_AGENTS),
        "llm_providers": providers,
        "blockchain_connected": connected,
        "contracts_deployed": kite_client.contracts_deployed,
        "verified_intent": True,
    })

    # === Step 8: Market Pulse (autonomous trigger) ===
    # Background loop that periodically fires a watchlist query through the
    # full orchestrator pipeline — real mandates, real x402 payments, real
    # audit trails, no human in the loop. Disabled via PULSE_ENABLED=false.
    if settings.pulse_enabled:
        from backend.pulse.scheduler import pulse_scheduler
        app.state.pulse_task = asyncio.create_task(pulse_scheduler.run())
        print(
            f"[Pulse] Autonomous trigger: ACTIVE "
            f"(initial delay {settings.pulse_initial_delay_seconds}s, "
            f"then every {settings.pulse_interval_seconds}s)"
        )
    else:
        print("[Pulse] Autonomous trigger: DISABLED (PULSE_ENABLED=false)")

    yield

    # Shutdown
    print("[Server] Shutting down Nexus economy...")
    sync_task = getattr(app.state, "catalog_sync_task", None)
    if sync_task is not None:
        sync_task.cancel()
        try:
            await sync_task
        except (asyncio.CancelledError, Exception):
            pass
    pulse_task = getattr(app.state, "pulse_task", None)
    if pulse_task is not None:
        pulse_task.cancel()
        try:
            await pulse_task
        except (asyncio.CancelledError, Exception):
            pass
    await data_agent.cleanup()
    await audit_agent.cleanup()


# ============================================================
# FastAPI App
# ============================================================
app = FastAPI(
    title="NEXUS - The Living Agent Economy",
    description="A self-sustaining micro-economy where AI agents operate as independent businesses on Kite Chain",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — in production, restrict to the explicit frontend origin set by
# FRONTEND_URL in .env.prod. In dev (localhost), keep it permissive so any
# origin on the same machine can hit the API. The combination of
# allow_origins=["*"] with allow_credentials=True is spec-invalid and
# browsers silently reject requests; this explicit-origin form is safe.
_allowed_origins: list[str] = []
if settings.frontend_url:
    _allowed_origins.append(settings.frontend_url.rstrip("/"))
# Always include dev origins so `python -m backend.main` + `npm run dev` works
# without extra config.
for _dev in ("http://localhost:3000", "http://127.0.0.1:3000"):
    if _dev not in _allowed_origins:
        _allowed_origins.append(_dev)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# Request/Response Models
# ============================================================
class QueryRequest(BaseModel):
    query: str
    token: Optional[str] = None
    # Control automatic enrichment capabilities. "auto" (default) honors each
    # capability's author-declared enrichment_suggestions. "off" runs only the
    # primary specialists. A list names specific capabilities to include.
    enrichments: Optional[str] = "auto"


class GovernanceUpdate(BaseModel):
    max_spend_per_tx: Optional[float] = None
    max_spend_per_day: Optional[float] = None
    max_spend_per_agent: Optional[float] = None


# ============================================================
# API Endpoints
# ============================================================

@app.get("/")
async def root():
    return {
        "project": "NEXUS - The Living Agent Economy on Kite Chain",
        "hackathon": "Kite AI Global Hackathon 2026",
        "track": "Novel/Novelty",
        "agents": len(ALL_AGENTS),
        "status": "running",
        "blockchain": {
            "connected": kite_client.is_connected,
            "contracts_deployed": kite_client.contracts_deployed,
            "network": "Kite Aero Testnet (Chain ID 2368)",
            "explorer": "https://testnet.kitescan.ai/",
            "total_on_chain_txs": len(kite_client.tx_hashes),
        },
        "verified_intent": {
            "mandate_system": "active",
            "circuit_breaker": "active",
            "audit_trail": "on_chain" if kite_client.is_connected else "local",
            "active_mandates": len(mandate_manager.active_mandates),
            "completed_mandates": len(mandate_manager.completed_mandates),
        },
        "kite_integration": {
            "x402_protocol": True,
            "x402_scheme": "gokite-aa",
            "facilitator": "facilitator.pieverse.io",
            "test_usdt": settings.kite_test_usdt,
            "mcp_compatible": True,
            "mcp_server": settings.kite_mcp_url,
            "agent_passport": "kite-portal",
            "network": f"kite-testnet ({settings.kite_chain_id})",
            "x402_endpoints": 3,
        },
    }


@app.post("/api/query")
async def submit_query(request: QueryRequest):
    """
    Submit a query to the Nexus agent economy. Routes purely through the
    capability registry — no hardcoded agent list. Returns a full envelope-based
    report: `sections` contains one entry per invoked capability (success or
    failure), `output_fields` contains only fields some agent produced.
    """
    report = await report_agent.handle_request({
        "query": request.query,
        "enrichments": request.enrichments or "auto",
    })
    return report


@app.get("/api/capabilities")
async def get_capabilities():
    """
    Return the full live capability registry. One entry per unique capability
    name, listing all providers and the declared input/output schemas. The
    frontend reads this to render suggestion pills, input hints, and
    register-agent form validation.
    """
    from backend.marketplace.capability_registry import capability_registry
    by_name: dict[str, dict] = {}
    for spec in capability_registry.all_specs():
        entry = by_name.setdefault(spec.name, {
            "name": spec.name,
            "description": spec.description,
            "input_schema": spec.input_schema,
            "output_schema": spec.output_schema,
            "enrichment_suggestions": list(spec.enrichment_suggestions),
            "example_queries": [],
            "keywords": [],
            "providers": [],
        })
        for q in spec.example_queries:
            if q and q not in entry["example_queries"]:
                entry["example_queries"].append(q)
        for k in spec.keywords:
            if k and k not in entry["keywords"]:
                entry["keywords"].append(k)
        entry["providers"].append({
            "agent_id": spec.provider_agent_id,
            "agent_name": spec.provider_agent_name,
            "source": spec.provider_source,
            "reputation": spec.provider_reputation,
            "price_usdc": spec.price_usdc,
        })

    capabilities = list(by_name.values())
    capabilities.sort(key=lambda c: c["name"])
    return {
        "capabilities": capabilities,
        "total_capabilities": len(capabilities),
        "total_providers": sum(len(c["providers"]) for c in capabilities),
    }


@app.get("/api/example_queries")
async def get_example_queries(limit: int = 12):
    """
    Reputation-weighted sample of example_queries pulled from every registered
    agent's self-declared examples. Used by the frontend to build dynamic
    suggestion pills — nothing hardcoded.
    """
    from backend.marketplace.capability_registry import capability_registry
    items: list[tuple[str, str, int]] = []  # (query, capability, reputation)
    seen: set[str] = set()
    for spec in capability_registry.all_specs():
        for q in spec.example_queries:
            q_clean = (q or "").strip()
            if not q_clean or q_clean.lower() in seen:
                continue
            seen.add(q_clean.lower())
            items.append((q_clean, spec.name, spec.provider_reputation))
    # Sort by provider reputation desc; stable for equal reputations.
    items.sort(key=lambda x: -x[2])
    out = [
        {"query": q, "capability": cap, "reputation": rep}
        for q, cap, rep in items[:limit]
    ]
    return {"examples": out, "total": len(items)}


@app.get("/api/agents")
async def get_agents():
    """
    Return ALL agents in the unified catalog: in-process built-ins,
    HTTP-callback marketplace agents, AND on-chain-only agents that we
    discovered from the AgentRegistry contract but don't have invocation
    metadata for. The chain is the source of truth.
    """
    from backend.agent_catalog import agent_catalog
    agents = await agent_catalog.get_all()
    return {
        "agents": agents,
        "total_agents": len(agents),
    }


@app.get("/api/agents/{agent_id}")
async def get_agent(agent_id: str):
    """Get detailed info about a specific agent (any source type)."""
    from backend.agent_catalog import agent_catalog
    agents = await agent_catalog.get_all()
    for a in agents:
        if a["agent_id"] == agent_id or a.get("name") == agent_id:
            # Attach recent transactions for in-process agents (they have the list).
            info = dict(a)
            for orig_id, orig_agent in {
                "data_agent": data_agent, "analyst_agent": analyst_agent,
                "audit_agent": audit_agent,
                "report_agent": report_agent,
            }.items():
                if orig_agent.name == a["name"]:
                    info["transactions"] = [t.model_dump() for t in orig_agent.transactions[-20:]]
                    break
            return info
    return {"error": f"Agent {agent_id} not found"}


@app.get("/api/transactions")
async def get_transactions():
    """Get all transactions across all agents"""
    all_txs = []
    for agent in ALL_AGENTS:
        for tx in agent.transactions:
            all_txs.append(tx.model_dump())

    # Sort by timestamp (newest first)
    all_txs.sort(key=lambda x: x["timestamp"], reverse=True)
    return {
        "transactions": all_txs[:100],
        "total_count": len(all_txs),
    }


@app.get("/api/reputation")
async def get_reputation():
    """
    Reputation leaderboard. Serves from the unified agent_catalog cache,
    which is refreshed from the ReputationTracker contract every 60s by a
    background sync task. This keeps the endpoint fast (<100ms) while the
    chain remains the authoritative source. SQLite contributes only the
    per-agent `history` arrays.
    """
    from backend.agent_catalog import agent_catalog
    from backend.db import load_reputation_history

    agents = await agent_catalog.get_all()

    leaderboard: list[dict] = []
    for a in agents:
        history = await load_reputation_history(a.get("name", ""), limit=10)
        score = int(a.get("reputation_score", 0))
        jobs = int(a.get("total_jobs_completed", 0))
        leaderboard.append({
            "name": a.get("name"),
            "agent_id": a.get("agent_id"),
            "passport_id": a.get("passport_id"),
            "source": a.get("source_type", "unknown"),
            "reputation_score": score,
            "total_jobs": jobs,
            "total_earned": a.get("total_earned", 0.0),
            "history": history,
        })

    leaderboard.sort(key=lambda x: x["reputation_score"], reverse=True)
    return {
        "leaderboard": leaderboard,
        "source": "kite-onchain (catalog-cached, 60s refresh)",
        "chain_id": 2368,
    }


@app.get("/api/reputation/{agent_id}")
async def get_agent_reputation(agent_id: str):
    """
    Detailed reputation history for a specific agent. Reads from the catalog
    cache (refreshed from chain every 60s by the background sync) and pulls
    the full local history from SQLite. Never blocks on a live RPC call.
    """
    from backend.agent_catalog import agent_catalog
    from backend.db import load_reputation_history

    agents = await agent_catalog.get_all()
    match = None
    for a in agents:
        if a.get("agent_id") == agent_id or a.get("name") == agent_id:
            match = a
            break
    if not match:
        return {"error": f"Agent {agent_id} not found"}

    history = await load_reputation_history(match.get("name", ""), limit=200)
    return {
        "agent": match.get("name"),
        "agent_id": match.get("agent_id"),
        "passport_id": match.get("passport_id"),
        "current_score": int(match.get("reputation_score", 0)),
        "total_jobs": int(match.get("total_jobs_completed", 0)),
        "history": history,
        "source": "catalog-cached (chain refresh: background 60s)",
        "scoring_rules": {
            "audit_score_90_plus": "+2 points (high quality)",
            "audit_score_70_plus": "+1 point (adequate quality)",
            "audit_score_below_70": "-3 points (low quality)",
            "marketplace_failure": "-2 points (timeout/error/unreachable)",
            "max_score": 100,
            "min_score": 0,
        },
    }


@app.get("/api/blockchain")
async def get_blockchain_status():
    """Get real blockchain status - judges can verify all transactions here"""
    on_chain_payments = await kite_client.get_payment_count()
    return {
        "connected": kite_client.is_connected,
        "contracts_deployed": kite_client.contracts_deployed,
        "network": {
            "name": "Kite Aero Testnet",
            "chain_id": 2368,
            "rpc": "https://rpc-testnet.gokite.ai/",
            "explorer": "https://testnet.kitescan.ai/",
        },
        "contracts": {
            "AgentRegistry": settings.agent_registry_address,
            "ReputationTracker": settings.reputation_tracker_address,
            "PaymentRouter": settings.payment_router_address,
            "GovernanceRules": settings.governance_rules_address,
        },
        "on_chain_transactions": kite_client.get_all_tx_hashes(),
        "on_chain_payment_count": on_chain_payments,
        "total_txs_sent": len(kite_client.tx_hashes),
        "x402": {
            "test_usdt_token": settings.kite_test_usdt,
            "facilitator": settings.facilitator_url,
            "facilitator_address": settings.facilitator_address,
        },
    }


@app.get("/api/stats")
async def get_stats():
    """
    Economy-wide statistics. Serves instantly from the agent_catalog cache
    (refreshed from chain every 60s in the background). An on-chain snapshot
    is added ONLY if it's already cached (<20s old); never blocks the
    response on an RPC round-trip.
    """
    from backend.agent_catalog import agent_catalog
    from backend.blockchain.chain_reader import chain_reader

    # Never block on chain — use whatever snapshot the background refresher has.
    cached_snap = await chain_reader.get_economy_snapshot_cached(max_age_seconds=60.0)
    onchain: dict = {}
    if cached_snap is not None:
        onchain = {
            "payment_count": cached_snap.payment_count,
            "total_volume_usdc": cached_snap.total_volume_usdc,
            "total_agents": cached_snap.total_agents,
            "top_earners": cached_snap.top_earners,
            "chain_id": cached_snap.chain_id,
        }

    catalog_stats = await agent_catalog.get_economy_stats()
    return {
        **catalog_stats,
        "onchain": onchain,
        "active_mandates": len(mandate_manager.active_mandates),
        "completed_mandates": len(mandate_manager.completed_mandates),
        "governance": report_agent.governance,
        "source": "catalog-cached (chain refresh: background 60s)",
    }


@app.post("/api/governance")
async def update_governance(update: GovernanceUpdate):
    """Update governance rules - both locally AND on-chain"""
    rules = {}
    tx_hashes = []

    if update.max_spend_per_tx is not None:
        rules["max_spend_per_tx"] = update.max_spend_per_tx
        # Write to blockchain
        tx = await kite_client.update_max_per_tx(update.max_spend_per_tx)
        if tx:
            tx_hashes.append(tx)

    if update.max_spend_per_day is not None:
        rules["max_spend_per_day"] = update.max_spend_per_day
        # Write to blockchain (GovernanceRules.setGlobalMaxPerDay)
        tx = await kite_client.update_max_per_day(update.max_spend_per_day)
        if tx:
            tx_hashes.append(tx)

    if update.max_spend_per_agent is not None:
        rules["max_spend_per_agent"] = update.max_spend_per_agent

    report_agent.update_governance(rules)

    from backend.models.events import NexusEvent, EventType
    await ws_manager.broadcast(NexusEvent(
        event_type=EventType.GOVERNANCE_RULE_CHANGED,
        data={"updated_rules": rules, "on_chain_txs": tx_hashes},
        message=f"Governance rules updated on-chain: {rules}",
    ))

    return {
        "status": "updated",
        "governance": report_agent.governance,
        "on_chain_txs": tx_hashes,
    }


# /api/alerts endpoints removed. AlertAgent is not registered because it
# promises notification delivery (email/push/SMS) that the current stack
# does not implement. Re-add when a real notification channel is wired up.


@app.get("/api/events")
async def get_recent_events():
    """Get recent event history"""
    return {
        "events": ws_manager.event_history[-50:],
        "total": len(ws_manager.event_history),
    }


@app.get("/api/onchain-history")
async def onchain_history(limit: int = 50):
    """
    Return historical payments from the PaymentRouter contract, newest first.
    Used by the dashboard's "On-chain History" tab (kept separate from the
    live WebSocket feed so old chain events don't interleave with current
    session activity).
    """
    from backend.agent_catalog import agent_catalog

    try:
        raw_payments = await kite_client.get_all_payments_from_chain(limit=limit)
    except Exception as e:
        return {"payments": [], "error": str(e), "source": "kite_chain", "chain_id": 2368}

    # Build passport_hex -> agent_name lookup so users see real names instead
    # of raw 0x-prefixed hashes.
    passport_to_name: dict[str, str] = {}
    try:
        for a in await agent_catalog.get_all():
            pid = (a.get("passport_id") or "").lower().lstrip("0x")
            if pid and a.get("name"):
                passport_to_name[pid] = a["name"]
    except Exception:
        pass

    from datetime import datetime, timezone as _tz
    payments = []
    for p in raw_payments:
        from_pid = (p.get("from_passport") or "").lower().lstrip("0x")
        to_pid = (p.get("to_passport") or "").lower().lstrip("0x")
        ts_unix = int(p.get("timestamp") or 0)
        iso = (
            datetime.fromtimestamp(ts_unix, tz=_tz.utc).isoformat()
            if ts_unix > 0 else None
        )
        payments.append({
            "index": p.get("index"),
            "from_passport": from_pid,
            "from_agent": passport_to_name.get(from_pid),
            "to_passport": to_pid,
            "to_agent": passport_to_name.get(to_pid),
            "amount_usdc": p.get("amount"),
            "purpose": p.get("purpose"),
            "mandate_id": p.get("mandate_id"),
            "timestamp_iso": iso,
            "timestamp_unix": ts_unix,
        })

    return {
        "payments": payments,
        "total": len(payments),
        "source": "kite_chain",
        "chain_id": 2368,
        "explorer_base": "https://testnet.kitescan.ai",
    }


# ============================================================
# Market Pulse API — autonomous trigger runs
# ============================================================

import time as _time_for_pulse  # for the per-IP rate limiter below
from fastapi import Request as _PulseRequest
from fastapi.responses import JSONResponse as _PulseJSONResponse

# In-memory per-IP rate limiter for manual trigger. Dies on restart — good
# enough for a demo. Prevents a judge accidentally DoS'ing the faucet wallet
# by spamming the "Trigger run now" button.
_pulse_trigger_last_call_by_ip: dict[str, float] = {}
_PULSE_TRIGGER_MIN_INTERVAL_SEC = 60


@app.get("/api/pulse")
async def pulse_list(limit: int = 50):
    """
    Return the most recent Market Pulse runs — newest first. Each row is one
    fully-orchestrated, fully-settled run: mandate + x402 payments + audit
    trail recorded on Kite testnet. The /pulse page renders this.
    """
    from backend.pulse.store import load_pulse_runs, count_pulse_runs
    runs = await load_pulse_runs(limit=limit)
    total = await count_pulse_runs()
    return {
        "runs": runs,
        "total": total,
        "explorer_base": "https://testnet.kitescan.ai",
    }


@app.get("/api/pulse/status")
async def pulse_status():
    """Current scheduler state — interval, next/last run time, total runs."""
    from backend.pulse.scheduler import pulse_scheduler
    return pulse_scheduler.status()


@app.post("/api/pulse/trigger")
async def pulse_trigger(request: _PulseRequest):
    """
    Fire one run immediately, bypassing the scheduled interval. Returns the
    persisted run dict. Rate-limited in memory to 1 call per minute per IP.

    The query used is the NEXT one in the watchlist — same rotation as the
    scheduler — so manual triggers still exercise the full watchlist over time.
    """
    from backend.pulse.scheduler import pulse_scheduler
    from backend.pulse.watchlist import pick

    client_ip = "unknown"
    try:
        if request.client is not None:
            client_ip = request.client.host or "unknown"
    except Exception:
        pass

    now_ts = _time_for_pulse.time()
    last = _pulse_trigger_last_call_by_ip.get(client_ip, 0.0)
    if now_ts - last < _PULSE_TRIGGER_MIN_INTERVAL_SEC:
        retry_after = int(_PULSE_TRIGGER_MIN_INTERVAL_SEC - (now_ts - last))
        return _PulseJSONResponse(
            status_code=429,
            content={
                "error": "rate_limited",
                "message": (
                    f"Manual trigger limited to 1 per "
                    f"{_PULSE_TRIGGER_MIN_INTERVAL_SEC}s. "
                    f"Try again in {retry_after}s."
                ),
                "retry_after_seconds": retry_after,
            },
        )
    _pulse_trigger_last_call_by_ip[client_ip] = now_ts

    # v2: no rotation index — manual triggers generate a fresh query the
    # same way scheduled runs do (LLM → registry → built-in). The judge
    # clicking "Trigger run now" sees a novel query, not a cycled one.
    from backend.pulse.query_generator import generate_query
    query, query_source = await generate_query()

    run = await pulse_scheduler.run_once(
        query, trigger_source="manual", query_source=query_source,
    )
    return run


# Route ORDER matters here. FastAPI matches paths in declaration order,
# so the path-variable form `/api/pulse/{run_id}` MUST come after the
# specific routes `/api/pulse/status` and `/api/pulse/trigger` — otherwise
# "status" or "trigger" would be captured as a run_id.
@app.get("/api/pulse/{run_id}")
async def pulse_run_detail(run_id: str):
    """
    Return a single pulse run with full drill-down detail:
      - the persisted row (IDs, summary, per-payment breakdown)
      - live mandate details (ECDSA signature, signer, budget, payment log
        with circuit-breaker decisions) if the mandate is still in memory
      - audit trail entry (traceability hash, report hash, on-chain tx)
        if still in memory

    Mandate + audit lookups use the in-memory managers; older runs whose
    mandates have been purged will return `mandate_detail: null` — that's
    transparent, not an error.
    """
    from backend.pulse.store import load_pulse_run
    run = await load_pulse_run(run_id)
    if not run:
        return _PulseJSONResponse(
            status_code=404,
            content={"error": "not_found", "message": f"Pulse run {run_id} not found"},
        )

    # --- Join: live mandate detail ---
    mandate_detail = None
    if run.get("mandate_id"):
        try:
            m = mandate_manager.get_mandate(run["mandate_id"])
            if m is not None:
                mandate_detail = m.model_dump(mode="json")
        except Exception as e:
            print(f"[Pulse] Mandate lookup failed for {run['mandate_id']}: {e}")
    run["mandate_detail"] = mandate_detail

    # --- Join: audit trail detail ---
    audit_detail = None
    audit_tx = run.get("audit_tx_hash")
    if audit_tx:
        try:
            for t in audit_trail_builder.trails:
                if t.on_chain_tx_hash == audit_tx:
                    audit_detail = t.model_dump(mode="json")
                    break
        except Exception as e:
            print(f"[Pulse] Audit lookup failed for tx {audit_tx[:12]}...: {e}")
    run["audit_trail_detail"] = audit_detail

    run["explorer_base"] = "https://testnet.kitescan.ai"
    return run


# ============================================================
# Verified Intent API Endpoints
# ============================================================

@app.get("/api/mandates")
async def list_mandates():
    """List all mandates (active and completed)"""
    active = [m.model_dump(mode="json") for m in mandate_manager.active_mandates.values()]
    completed = [m.model_dump(mode="json") for m in mandate_manager.completed_mandates[-20:]]
    return {
        "active": active,
        "completed": completed,
        "total_active": len(active),
        "total_completed": len(mandate_manager.completed_mandates),
    }


@app.get("/api/mandate/{mandate_id}")
async def get_mandate(mandate_id: str):
    """Get details of a specific mandate"""
    mandate = mandate_manager.get_mandate(mandate_id)
    if not mandate:
        return {"error": f"Mandate {mandate_id} not found"}
    return mandate.model_dump(mode="json")


@app.get("/api/audit-trail")
async def get_audit_trail():
    """Get all audit trail entries - each verifiable on block explorer"""
    return {
        "trails": [t.model_dump(mode="json") for t in audit_trail_builder.trails[-20:]],
        "total": len(audit_trail_builder.trails),
    }


@app.get("/api/audit-trail/{trail_id}")
async def get_audit_trail_entry(trail_id: str):
    """Get a specific audit trail entry"""
    for t in audit_trail_builder.trails:
        if t.trail_id == trail_id:
            return t.model_dump(mode="json")
    return {"error": f"Trail {trail_id} not found"}


@app.get("/api/agent-identity/{agent_id}")
async def get_agent_identity(agent_id: str):
    """Get the full DID document for an agent (W3C-inspired)"""
    for agent in ALL_AGENTS:
        if agent.agent_id == agent_id:
            if agent.passport_id:
                did_doc = agent_identity_resolver.resolve_did_document(
                    agent_name=agent.name,
                    passport_hex=agent.passport_id,
                    controller_address=kite_client.account.address if kite_client.account else "unknown",
                    capabilities=agent.capabilities,
                    reputation_score=agent.reputation_score,
                )
                return did_doc
            return {"error": "Agent not registered on-chain", "agent": agent.name}
    return {"error": f"Agent {agent_id} not found"}


@app.get("/api/did/{did_string:path}")
async def resolve_did(did_string: str):
    """Resolve any DID to its document"""
    doc = agent_identity_resolver.lookup(did_string)
    if doc:
        return doc
    return {"error": f"DID not found: {did_string}"}


@app.post("/api/verify-mandate")
async def verify_mandate(mandate_id: str):
    """Verify a mandate's ECDSA signature is valid"""
    mandate = mandate_manager.get_mandate(mandate_id)
    if not mandate:
        return {"error": "Mandate not found", "mandate_id": mandate_id}

    if mandate.signature == "unsigned":
        return {"mandate_id": mandate_id, "signature_valid": False, "reason": "Mandate was not signed (no deployer key)"}

    try:
        from eth_account.messages import encode_defunct
        from eth_account import Account as EthAccount
        message_text = (
            f"NEXUS_MANDATE:{mandate.mandate_id}:{mandate.context_hash}:"
            f"{mandate.total_budget}:{mandate.max_per_tx}:{mandate.expires_at.isoformat()}"
        )
        message = encode_defunct(text=message_text)
        sig_hex = mandate.signature[2:] if mandate.signature.startswith("0x") else mandate.signature
        recovered = EthAccount.recover_message(message, signature=bytes.fromhex(sig_hex))
        valid = recovered.lower() == mandate.signer_address.lower()
    except Exception:
        valid = False

    return {
        "mandate_id": mandate_id,
        "signature_valid": valid,
        "signer": mandate.signer_address,
    }


@app.get("/api/circuit-breaker")
async def get_circuit_breaker_stats():
    """Get circuit breaker statistics"""
    return {
        "approvals": circuit_breaker.approval_count,
        "blocks": circuit_breaker.block_count,
        "recent_blocks": [
            b.model_dump(mode="json") for b in circuit_breaker.block_log[-10:]
        ],
    }


# ============================================================
# Agent Marketplace API
# ============================================================

class MarketplaceRegisterRequest(BaseModel):
    name: str
    description: str
    capabilities: list[str]
    price_per_query: float
    callback_url: str
    owner_address: str = ""
    # Self-describing routing metadata (makes discovery dynamic).
    keywords: list[str] = []
    example_queries: list[str] = []
    # Optional: rich capability specifications. When present, each entry shapes
    # routing (input/output schema), pricing, enrichments, and timeouts. The
    # orchestrator validates agent input against this schema before paying.
    # Omit for back-compat; `capabilities` as plain strings still works.
    capability_specs: list[dict] = []


@app.post("/api/marketplace/register")
async def marketplace_register(request: MarketplaceRegisterRequest):
    """
    Register a new external agent. Any capability name the agent declares
    becomes immediately routable — no backend code change required.
    """
    agent = await marketplace.register_agent(
        name=request.name,
        description=request.description,
        capabilities=request.capabilities,
        price_per_query=request.price_per_query,
        callback_url=request.callback_url,
        owner_address=request.owner_address,
        keywords=request.keywords,
        example_queries=request.example_queries,
        capability_specs=request.capability_specs,
    )
    return agent.model_dump(mode="json")


@app.get("/api/marketplace/agents")
async def marketplace_list_agents():
    """List all agents in the marketplace"""
    return {
        "agents": marketplace.get_all_agents(),
        "stats": marketplace.get_stats(),
    }


@app.get("/api/marketplace/discover")
async def marketplace_discover(
    capability: str,
    min_reputation: int = 0,
    max_price: float = 1.0,
):
    """Discover agents by capability, reputation, and price"""
    agents = marketplace.discover_agents(capability, min_reputation, max_price)
    return {
        "capability": capability,
        "matches": [a.model_dump(mode="json") for a in agents],
        "total": len(agents),
    }


@app.post("/api/marketplace/invoke/{agent_id}")
async def marketplace_invoke(agent_id: str, request: dict):
    """Invoke an external agent by its marketplace ID"""
    result = await marketplace.invoke_agent(agent_id, request)
    return result


@app.get("/api/marketplace/stats")
async def marketplace_stats():
    """Get marketplace-wide statistics"""
    return marketplace.get_stats()


@app.get("/api/wallets")
async def get_agent_wallets():
    """Get all derived agent wallets"""
    from backend.blockchain.agent_wallets import agent_wallet_manager
    return {
        "wallets": agent_wallet_manager.get_all_wallets(),
        "total": len(agent_wallet_manager.wallets),
        "type": "derived_eoa",
        "wallet_type": "deterministic_eoa",
    }


@app.post("/api/discover")
async def discover_agents_for_query(request: QueryRequest):
    """Preview which agents would be selected for a query (without executing)."""
    from backend.marketplace.discovery import discovery_engine
    classification = await discovery_engine.classify_query(
        request.query, user_enrichment_pref=request.enrichments or "auto",
    )
    return discovery_engine.build_execution_plan(classification)


# ============================================================
# x402 Protocol Endpoints (Kite-compliant)
# ============================================================
from fastapi import Request
from backend.x402.middleware import build_402_response, process_x402_payment
from backend.x402.schemas import DATA_AGENT_SCHEMA, ANALYST_AGENT_SCHEMA, AUDIT_AGENT_SCHEMA


@app.post("/x402/data-agent")
async def x402_data_agent(request: Request):
    """x402-compliant DataAgent - returns 402 without payment, data with payment"""
    payment = await process_x402_payment(request)
    if not payment["success"]:
        return build_402_response(
            agent_name="Nexus-DataAgent-v1",
            description="Collects real-time crypto data: Twitter sentiment, prices, whale activity, news",
            price_wei="100000000000000",  # 0.0001 USDT in wei
            payto_address=data_agent.wallet_address or (kite_client.account.address if kite_client.account else settings.facilitator_address),
            resource_url=f"{settings.public_url}/x402/data-agent",
            output_schema=DATA_AGENT_SCHEMA,
        )
    body = await request.json()
    result = await data_agent.handle_request(body)
    return result


@app.post("/x402/analyst-agent")
async def x402_analyst_agent(request: Request):
    """x402-compliant AnalystAgent - sentiment, technical analysis, whale interpretation"""
    payment = await process_x402_payment(request)
    if not payment["success"]:
        return build_402_response(
            agent_name="Nexus-AnalystAgent-v1",
            description="AI-powered analysis: sentiment (VADER+crypto), RSI, MACD, Bollinger, whale signals",
            price_wei="200000000000000",  # 0.0002 USDT in wei
            payto_address=analyst_agent.wallet_address or (kite_client.account.address if kite_client.account else settings.facilitator_address),
            resource_url=f"{settings.public_url}/x402/analyst-agent",
            output_schema=ANALYST_AGENT_SCHEMA,
        )
    body = await request.json()
    result = await analyst_agent.handle_request(body)
    return result


@app.post("/x402/audit-agent")
async def x402_audit_agent(request: Request):
    """x402-compliant AuditAgent - independent quality verification"""
    payment = await process_x402_payment(request)
    if not payment["success"]:
        return build_402_response(
            agent_name="Nexus-AuditAgent-v1",
            description="Independent quality audit: data freshness, sentiment accuracy, price verification",
            price_wei="100000000000000",  # 0.0001 USDT in wei
            payto_address=audit_agent.wallet_address or (kite_client.account.address if kite_client.account else settings.facilitator_address),
            resource_url=f"{settings.public_url}/x402/audit-agent",
            output_schema=AUDIT_AGENT_SCHEMA,
        )
    body = await request.json()
    result = await audit_agent.handle_request(body)
    return result


@app.get("/api/x402-status")
async def x402_status():
    """Shows x402 integration status - judges can verify Kite protocol compliance"""
    return {
        "protocol": "x402",
        "version": 1,
        "scheme": "gokite-aa",
        "network": "kite-testnet",
        "chain_id": 2368,
        "facilitator": settings.facilitator_url,
        "facilitator_address": settings.facilitator_address,
        "test_usdt_token": settings.kite_test_usdt,
        "mcp_server": settings.kite_mcp_url,
        "mcp_tools": ["get_payer_addr", "approve_payment"],
        "x402_endpoints": [
            {
                "agent": "Nexus-DataAgent-v1",
                "url": "/x402/data-agent",
                "price_usdt": "0.0001",
                "capabilities": data_agent.capabilities,
            },
            {
                "agent": "Nexus-AnalystAgent-v1",
                "url": "/x402/analyst-agent",
                "price_usdt": "0.0002",
                "capabilities": analyst_agent.capabilities,
            },
            {
                "agent": "Nexus-AuditAgent-v1",
                "url": "/x402/audit-agent",
                "price_usdt": "0.0001",
                "capabilities": audit_agent.capabilities,
            },
        ],
    }


# ============================================================
# WebSocket - Real-time dashboard updates
# ============================================================
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time dashboard updates.
    Every agent action, payment, and audit result is pushed here.
    """
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive, handle any incoming messages from dashboard
            data = await websocket.receive_text()
            # Could handle dashboard commands here (e.g., governance updates)
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


# ============================================================
# Run with: python -m backend.main
# ============================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=settings.backend_host,
        port=settings.backend_port,
        reload=True,
        access_log=False,  # Suppress noisy per-request GET/POST logs from polling
    )

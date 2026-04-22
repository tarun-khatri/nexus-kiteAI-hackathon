"""
NEXUS - Agent Marketplace Registry
Manages external agent registration, discovery, and invocation.

How it works:
1. Anyone registers an agent: name, capabilities, price, callback_url
2. Agent gets registered on-chain in AgentRegistry contract
3. When NEXUS needs a capability, it queries registered agents
4. Picks best agent by reputation + price
5. Calls agent's callback_url with the work request
6. Agent returns JSON result
7. Payment made on-chain, reputation updated

This is the "Uber for AI agents" - anyone can be a service provider.
"""

import uuid
import httpx
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

from backend.blockchain.kite_client import kite_client


class ExternalAgent(BaseModel):
    """An externally registered agent in the marketplace"""
    agent_id: str
    name: str
    description: str
    capabilities: list[str]
    price_per_query: float
    callback_url: str
    owner_address: str
    # Self-describing routing: agents tell the backend which keywords / example
    # queries should route to them. This makes the discovery engine fully dynamic
    # -- no backend code changes needed when new agents are registered.
    keywords: list[str] = Field(default_factory=list)
    example_queries: list[str] = Field(default_factory=list)
    # Rich capability declarations. When present, each entry shapes routing
    # (input/output schema), pricing, and enrichment suggestions. Optional:
    # legacy registrations with only `capabilities: ["x","y"]` still work.
    capability_specs: list[dict] = Field(default_factory=list)
    passport_id: Optional[str] = None
    reputation_score: int = 50
    total_jobs: int = 0
    active: bool = True
    registered_at: datetime = Field(default_factory=datetime.utcnow)
    last_invoked: Optional[datetime] = None


class AgentMarketplace:
    """
    Open marketplace for AI agents.
    Handles registration, discovery, invocation, and reputation management.
    """

    def __init__(self):
        self.external_agents: dict[str, ExternalAgent] = {}
        self.invocation_log: list[dict] = []
        self.http_client = httpx.AsyncClient(timeout=30.0)

    async def register_agent(
        self,
        name: str,
        description: str,
        capabilities: list[str],
        price_per_query: float,
        callback_url: str,
        owner_address: str = "",
        keywords: list[str] = None,
        example_queries: list[str] = None,
        capability_specs: list[dict] = None,
    ) -> ExternalAgent:
        """
        Register a new external agent in the marketplace.
        Also registers on-chain in AgentRegistry contract.

        Agents self-describe their routing by providing:
        - keywords: words that indicate a query should route to this agent
        - example_queries: sample queries this agent can handle
        The discovery engine uses these dynamically -- no backend code changes needed.
        """
        # Deduplicate by name. If this agent name is already registered
        # (e.g. after a container restart where the agent re-registers),
        # UPDATE the existing record in place instead of creating a new row.
        # This prevents "9 DEXScreener entries, each at rep=50" bugs where
        # reputation updates go to one stale copy and the UI reads another.
        existing_id = None
        existing_rep: Optional[int] = None
        existing_jobs: Optional[int] = None
        for aid, ext in list(self.external_agents.items()):
            if ext.name == name:
                existing_id = aid
                existing_rep = ext.reputation_score
                existing_jobs = ext.total_jobs
                # Remove the stale duplicate(s) — we'll re-register as one.
                self.external_agents.pop(aid, None)

        agent_id = existing_id or f"ext-{uuid.uuid4().hex[:12]}"

        agent = ExternalAgent(
            agent_id=agent_id,
            name=name,
            description=description,
            capabilities=capabilities,
            price_per_query=price_per_query,
            callback_url=callback_url,
            owner_address=owner_address or "unknown",
            keywords=keywords or [],
            example_queries=example_queries or [],
            capability_specs=capability_specs or [],
            # Preserve accumulated reputation + job counter across re-registrations.
            reputation_score=existing_rep if existing_rep is not None else 50,
            total_jobs=existing_jobs if existing_jobs is not None else 0,
        )

        # Register on-chain
        tx_hash = await kite_client.register_agent(
            name, description, capabilities, price_per_query
        )
        if tx_hash:
            agent.passport_id = kite_client._get_passport_id(name).hex()
            print(f"[Marketplace] Agent '{name}' registered on-chain: {tx_hash[:16]}...")
        else:
            # Registration may have failed because the agent is already on-chain
            # from a previous run. Cache the deterministic passport ID so it's
            # still linked to the on-chain entry.
            try:
                agent.passport_id = kite_client._get_passport_id(name).hex()
            except Exception:
                pass

        self.external_agents[agent_id] = agent
        print(f"[Marketplace] Registered: {name} ({agent_id}) | Capabilities: {capabilities} | Price: ${price_per_query}")

        # Rebuild capability registry so the new agent is routable immediately.
        try:
            from backend.marketplace.discovery import rebuild_capability_registry
            total = rebuild_capability_registry()
            print(f"[Marketplace] Capability registry rebuilt: {total} spec(s)")
        except Exception as e:
            print(f"[Marketplace] Capability registry rebuild warning: {e}")

        # Persist registration so the marketplace survives backend restarts.
        try:
            from backend.db import save_marketplace_agent
            await save_marketplace_agent({
                "agent_id": agent.agent_id,
                "name": agent.name,
                "description": agent.description,
                "capabilities": list(agent.capabilities),
                "keywords": list(agent.keywords or []),
                "example_queries": list(agent.example_queries or []),
                "price_per_query": agent.price_per_query,
                "callback_url": agent.callback_url,
                "owner_address": agent.owner_address,
                "passport_id": agent.passport_id,
                "reputation_score": agent.reputation_score,
                "total_jobs": agent.total_jobs,
                "active": agent.active,
                "registered_at": agent.registered_at.isoformat() if agent.registered_at else None,
                "last_invoked": agent.last_invoked.isoformat() if agent.last_invoked else None,
            })
        except Exception as e:
            print(f"[Marketplace] DB persist warning: {e}")

        return agent

    def hydrate_from_persisted(self, persisted_agents: list[dict]) -> int:
        """
        Rehydrate marketplace.external_agents from SQLite on backend startup.
        Deduplicates by name: earlier SQLite rows have stacked up across
        restarts (one per re-registration). Keep only the most-recent row per
        agent name, preserving accumulated reputation + job counts.
        """
        # Sort oldest first; later rows overwrite earlier ones.
        sorted_rows = sorted(
            persisted_agents,
            key=lambda r: r.get("registered_at") or "",
        )
        by_name: dict[str, dict] = {}
        for row in sorted_rows:
            name = (row.get("name") or "").strip()
            if not name:
                continue
            prev = by_name.get(name)
            if prev is None:
                by_name[name] = dict(row)
                continue
            # Carry forward whichever had more jobs (freshest state).
            merged = dict(row)
            merged["reputation_score"] = max(
                int(row.get("reputation_score", 50) or 50),
                int(prev.get("reputation_score", 50) or 50),
            )
            merged["total_jobs"] = max(
                int(row.get("total_jobs", 0) or 0),
                int(prev.get("total_jobs", 0) or 0),
            )
            by_name[name] = merged

        count = 0
        for row in by_name.values():
            aid = row.get("agent_id")
            if not aid or aid in self.external_agents:
                continue
            try:
                ext = ExternalAgent(
                    agent_id=aid,
                    name=row.get("name", ""),
                    description=row.get("description", ""),
                    capabilities=row.get("capabilities") or [],
                    price_per_query=row.get("price_per_query", 0),
                    callback_url=row.get("callback_url", ""),
                    owner_address=row.get("owner_address", "") or "unknown",
                    keywords=row.get("keywords") or [],
                    example_queries=row.get("example_queries") or [],
                    passport_id=row.get("passport_id") or None,
                    reputation_score=row.get("reputation_score", 50),
                    total_jobs=row.get("total_jobs", 0),
                    active=row.get("active", True),
                )
                # registered_at + last_invoked are datetime fields; parse if present.
                from datetime import datetime as _dt
                if row.get("registered_at"):
                    try:
                        ext.registered_at = _dt.fromisoformat(row["registered_at"])
                    except Exception:
                        pass
                if row.get("last_invoked"):
                    try:
                        ext.last_invoked = _dt.fromisoformat(row["last_invoked"])
                    except Exception:
                        pass
                self.external_agents[aid] = ext
                count += 1
            except Exception as e:
                print(f"[Marketplace] Hydrate skipped {aid}: {e}")

        # After hydration, rebuild the capability registry so restored agents
        # are routable without waiting for a new registration event.
        if count:
            try:
                from backend.marketplace.discovery import rebuild_capability_registry
                rebuild_capability_registry()
            except Exception as e:
                print(f"[Marketplace] post-hydrate rebuild warning: {e}")
        return count

    def discover_agents(
        self,
        capability: str,
        min_reputation: int = 0,
        max_price: float = float('inf'),
    ) -> list[ExternalAgent]:
        """
        Discover agents by capability, filtered by reputation and price.
        Returns agents sorted by reputation (highest first), then price (lowest first).
        """
        matches = []
        for agent in self.external_agents.values():
            if not agent.active:
                continue
            if capability in agent.capabilities:
                if agent.reputation_score >= min_reputation:
                    if agent.price_per_query <= max_price:
                        matches.append(agent)

        # Sort: highest reputation first, then lowest price
        matches.sort(key=lambda a: (-a.reputation_score, a.price_per_query))
        return matches

    async def invoke_agent(
        self, agent_id: str, request_data: dict, use_x402: bool = False,
    ) -> dict:
        """
        Invoke an external agent by calling its callback URL.
        If use_x402=True, uses x402 protocol (Kite-compliant) for payment.
        Returns the agent's response or an error dict.
        """
        agent = self.external_agents.get(agent_id)
        if not agent:
            return {"error": f"Agent {agent_id} not found"}

        if not agent.active:
            return {"error": f"Agent {agent_id} is inactive"}

        try:
            # Use x402 payment protocol if enabled
            if use_x402:
                from backend.x402.client import x402_client
                print(f"[Marketplace] Invoking {agent.name} via x402 at {agent.callback_url}")
                return await x402_client.pay_and_call(agent.callback_url, request_data)

            print(f"[Marketplace] Invoking {agent.name} at {agent.callback_url}")
            response = await self.http_client.post(
                agent.callback_url,
                json=request_data,
                timeout=25.0,
            )

            if response.status_code == 200:
                result = response.json()
                agent.total_jobs += 1
                agent.last_invoked = datetime.utcnow()

                self.invocation_log.append({
                    "agent_id": agent_id,
                    "agent_name": agent.name,
                    "timestamp": datetime.utcnow().isoformat(),
                    "success": True,
                    "duration_ms": response.elapsed.total_seconds() * 1000 if response.elapsed else 0,
                })

                print(f"[Marketplace] {agent.name} responded successfully")
                return result
            else:
                return {"error": f"Agent returned HTTP {response.status_code}"}

        except httpx.TimeoutException:
            self._record_failure(agent, "Timeout")
            return {"error": f"Agent {agent.name} timed out"}
        except httpx.ConnectError:
            self._record_failure(agent, "Connection refused")
            return {"error": f"Agent {agent.name} unreachable at {agent.callback_url}"}
        except Exception as e:
            self._record_failure(agent, str(e))
            return {"error": f"Agent invocation failed: {e}"}

    def _record_failure(self, agent: ExternalAgent, reason: str):
        """Record a failed invocation"""
        agent.reputation_score = max(0, agent.reputation_score - 2)
        self.invocation_log.append({
            "agent_id": agent.agent_id,
            "agent_name": agent.name,
            "timestamp": datetime.utcnow().isoformat(),
            "success": False,
            "error": reason,
        })
        print(f"[Marketplace] {agent.name} FAILED: {reason} (reputation: {agent.reputation_score})")

    def get_all_agents(self) -> list[dict]:
        """Get all marketplace agents as dicts"""
        return [a.model_dump(mode="json") for a in self.external_agents.values()]

    def get_stats(self) -> dict:
        """Get marketplace statistics"""
        active = [a for a in self.external_agents.values() if a.active]
        return {
            "total_agents": len(self.external_agents),
            "active_agents": len(active),
            "total_invocations": len(self.invocation_log),
            "successful_invocations": len([l for l in self.invocation_log if l.get("success")]),
            "capabilities": list(set(
                cap for a in active for cap in a.capabilities
            )),
        }


# Global singleton
marketplace = AgentMarketplace()

"""
NEXUS - Capability Registry

A runtime-built index of every capability offered by every agent currently
in the marketplace (built-in OR external). Rebuilt on every registration /
unregistration event. The discovery engine and the UI both read from here;
there is no hardcoded capability list anywhere else in the codebase.

A capability is identified by its string `name`. Multiple agents can offer
the same capability name; the registry tracks all providers and their
current reputations.

Each capability entry carries:
  - input_schema  : JSONSchema-ish spec for the agent's expected input
  - output_schema : JSONSchema-ish spec for what the agent returns
  - enrichment_suggestions : capabilities the author suggests run alongside
  - example_queries, keywords : hints surfaced to the LLM router

Backward-compat: legacy agents may register with a plain `capabilities: ["foo","bar"]`
list (no schemas). The registry synthesizes a minimal default schema in that case.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# Minimal fall-back schema used when a legacy agent registers capabilities
# as plain strings (no per-capability metadata). Gives the LLM + extractor
# enough structure to route queries; agents that want stricter validation
# declare their own schemas.
_DEFAULT_INPUT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "identifier": {"type": "string", "format": "string"},
    },
    "required": [],
}


@dataclass
class CapabilitySpec:
    """One capability declaration owned by a specific agent."""
    name: str
    description: str = ""
    input_schema: dict = field(default_factory=lambda: deepcopy(_DEFAULT_INPUT_SCHEMA))
    output_schema: dict = field(default_factory=dict)
    enrichment_suggestions: list[str] = field(default_factory=list)
    example_queries: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    price_usdc: float = 0.0
    timeout_ms: int = 30_000

    # Filled by the registry:
    provider_agent_id: str = ""
    provider_agent_name: str = ""
    provider_source: str = "builtin"  # "builtin" | "marketplace" | "on_chain_only"
    provider_reputation: int = 50

    def to_public_dict(self) -> dict:
        """Serializer for /api/capabilities. No provider internals leak."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "enrichment_suggestions": list(self.enrichment_suggestions),
            "example_queries": list(self.example_queries),
            "keywords": list(self.keywords),
            "price_usdc": self.price_usdc,
            "timeout_ms": self.timeout_ms,
            "provider": {
                "agent_id": self.provider_agent_id,
                "agent_name": self.provider_agent_name,
                "source": self.provider_source,
                "reputation": self.provider_reputation,
            },
        }


class CapabilityRegistry:
    """
    Runtime index: capability_name -> list[CapabilitySpec].
    Rebuild is O(n) in agents; cheap enough to do on every registration event.
    """

    def __init__(self):
        self._by_name: dict[str, list[CapabilitySpec]] = {}
        self._change_callbacks: list[Callable[[], None]] = []

    # ----- Rebuild -----

    def rebuild(
        self,
        builtin_agents: dict,
        external_agents: dict,
    ) -> int:
        """
        Rebuild the full index from the live agent pool.
        Returns total capability-specs indexed.
        """
        self._by_name.clear()

        # Built-in agents
        for agent_id, agent in (builtin_agents or {}).items():
            for spec in self._materialize_specs_from(agent, "builtin"):
                spec.provider_agent_id = agent_id
                spec.provider_agent_name = agent.name
                spec.provider_source = "builtin"
                spec.provider_reputation = int(getattr(agent, "reputation_score", 50))
                self._by_name.setdefault(spec.name, []).append(spec)

        # Marketplace agents
        for ext in (external_agents or {}).values():
            if not getattr(ext, "active", True):
                continue
            for spec in self._materialize_specs_from(ext, "marketplace"):
                spec.provider_agent_id = ext.agent_id
                spec.provider_agent_name = ext.name
                spec.provider_source = "marketplace"
                spec.provider_reputation = int(ext.reputation_score)
                self._by_name.setdefault(spec.name, []).append(spec)

        self._fire_changed()
        return sum(len(v) for v in self._by_name.values())

    # ----- Lookups -----

    def names(self) -> list[str]:
        return sorted(self._by_name.keys())

    def providers_for(self, capability_name: str) -> list[CapabilitySpec]:
        return list(self._by_name.get(capability_name, []))

    def all_specs(self) -> list[CapabilitySpec]:
        out: list[CapabilitySpec] = []
        for specs in self._by_name.values():
            out.extend(specs)
        return out

    def get_enrichment_suggestions(self, capability_name: str) -> list[str]:
        """Union of enrichment_suggestions declared by every provider of this capability."""
        seen: set[str] = set()
        for spec in self.providers_for(capability_name):
            for hint in spec.enrichment_suggestions:
                if hint and hint not in seen:
                    seen.add(hint)
        return sorted(seen)

    def pick_best_provider(
        self, capability_name: str, min_reputation: int = 0,
    ) -> Optional[CapabilitySpec]:
        """
        Pick the best-scoring provider for a capability.
        Sort: reputation desc, price asc.
        """
        candidates = [s for s in self.providers_for(capability_name)
                      if s.provider_reputation >= min_reputation]
        if not candidates:
            return None
        candidates.sort(key=lambda s: (-s.provider_reputation, s.price_usdc))
        return candidates[0]

    # ----- Change notification -----

    def on_change(self, callback: Callable[[], None]):
        self._change_callbacks.append(callback)

    def _fire_changed(self):
        for cb in self._change_callbacks:
            try:
                cb()
            except Exception as e:
                print(f"[CapabilityRegistry] change callback error: {e}")

    # ----- Spec materialization -----

    @staticmethod
    def _materialize_specs_from(agent: Any, source: str) -> list[CapabilitySpec]:
        """
        Read an agent object and return one CapabilitySpec per capability it offers.

        Supports two shapes:

        (1) Rich: `agent.capability_specs = [{name, input_schema, output_schema, ...}, ...]`
            The agent author has declared structured specs.

        (2) Legacy: `agent.capabilities = ["foo", "bar"]`
            Plain strings. We synthesize defaults so the system still works.
            The agent-level `keywords` and `example_queries` apply to all its
            capabilities.
        """
        # Preferred: structured specs
        specs_source = getattr(agent, "capability_specs", None)
        if isinstance(specs_source, list) and specs_source:
            out: list[CapabilitySpec] = []
            for entry in specs_source:
                if not isinstance(entry, dict):
                    continue
                out.append(CapabilitySpec(
                    name=str(entry.get("name", "")).strip(),
                    description=str(entry.get("description", "")),
                    input_schema=entry.get("input_schema") or deepcopy(_DEFAULT_INPUT_SCHEMA),
                    output_schema=entry.get("output_schema") or {},
                    enrichment_suggestions=list(entry.get("enrichment_suggestions") or []),
                    example_queries=list(entry.get("example_queries") or getattr(agent, "example_queries", []) or []),
                    keywords=list(entry.get("keywords") or getattr(agent, "keywords", []) or []),
                    price_usdc=float(entry.get("price_usdc",
                                              getattr(agent, "price_per_query", 0.0))),
                    timeout_ms=int(entry.get("timeout_ms", 30_000)),
                ))
            # Filter out broken empty-name entries.
            return [s for s in out if s.name]

        # Legacy fallback: one default spec per capability string
        capabilities = getattr(agent, "capabilities", None) or []
        keywords = list(getattr(agent, "keywords", []) or [])
        examples = list(getattr(agent, "example_queries", []) or [])
        price = float(getattr(agent, "price_per_query", 0.0))
        return [
            CapabilitySpec(
                name=str(cap).strip(),
                description=f"Capability '{cap}' provided by {getattr(agent, 'name', 'unknown')}",
                input_schema=deepcopy(_DEFAULT_INPUT_SCHEMA),
                output_schema={},
                enrichment_suggestions=[],
                example_queries=examples,
                keywords=keywords,
                price_usdc=price,
                timeout_ms=30_000,
            )
            for cap in capabilities
            if cap
        ]


# Global singleton
capability_registry = CapabilityRegistry()

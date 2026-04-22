"""
Tests for the capability registry — runtime-built index that lets any new
agent register any new capability name and be routable with zero code edits.
"""

from backend.marketplace.capability_registry import (
    CapabilityRegistry, CapabilitySpec,
)


class FakeAgent:
    """Minimal duck-typed stand-in for BaseAgent / ExternalAgent."""
    def __init__(self, name, capabilities, keywords=None, example_queries=None,
                 reputation_score=50, price_per_query=0.0001, capability_specs=None,
                 agent_id=None):
        self.name = name
        self.agent_id = agent_id or f"fake-{name.lower()}"
        self.capabilities = capabilities
        self.keywords = keywords or []
        self.example_queries = example_queries or []
        self.reputation_score = reputation_score
        self.price_per_query = price_per_query
        if capability_specs is not None:
            self.capability_specs = capability_specs
        self.active = True


def test_legacy_agent_synthesized_specs():
    """An agent with only plain capabilities: [...] still indexes correctly."""
    reg = CapabilityRegistry()
    reg.rebuild(
        builtin_agents={"a": FakeAgent("A", ["foo_cap", "bar_cap"], keywords=["k1"])},
        external_agents={},
    )
    assert "foo_cap" in reg.names()
    assert "bar_cap" in reg.names()
    spec = reg.providers_for("foo_cap")[0]
    assert spec.provider_agent_name == "A"
    assert spec.keywords == ["k1"]


def test_rich_specs_replace_defaults():
    reg = CapabilityRegistry()
    agent = FakeAgent(
        "B", ["thing"],
        capability_specs=[{
            "name": "thing",
            "description": "does a thing",
            "input_schema": {
                "type": "object",
                "properties": {"identifier": {"type": "string", "format": "evm_address"}},
                "required": ["identifier"],
            },
            "output_schema": {"type": "object"},
            "enrichment_suggestions": ["bar_cap"],
            "price_usdc": 0.0005,
            "timeout_ms": 12345,
        }],
    )
    reg.rebuild(builtin_agents={}, external_agents={"b": agent})
    spec = reg.providers_for("thing")[0]
    assert spec.description == "does a thing"
    assert spec.input_schema["properties"]["identifier"]["format"] == "evm_address"
    assert spec.enrichment_suggestions == ["bar_cap"]
    assert spec.price_usdc == 0.0005
    assert spec.timeout_ms == 12345


def test_multiple_providers_all_indexed():
    reg = CapabilityRegistry()
    a1 = FakeAgent("A1", ["common_cap"], reputation_score=60)
    a2 = FakeAgent("A2", ["common_cap"], reputation_score=90)
    reg.rebuild(builtin_agents={"a1": a1}, external_agents={"a2": a2})
    provs = reg.providers_for("common_cap")
    assert len(provs) == 2


def test_best_provider_picks_highest_reputation():
    reg = CapabilityRegistry()
    a1 = FakeAgent("Low", ["x"], reputation_score=40, price_per_query=0.0001)
    a2 = FakeAgent("High", ["x"], reputation_score=80, price_per_query=0.0002)
    reg.rebuild(builtin_agents={"a": a1}, external_agents={"b": a2})
    best = reg.pick_best_provider("x")
    assert best.provider_agent_name == "High"


def test_best_provider_ties_break_by_price():
    reg = CapabilityRegistry()
    a1 = FakeAgent("Cheap", ["x"], reputation_score=70, price_per_query=0.0001)
    a2 = FakeAgent("Expensive", ["x"], reputation_score=70, price_per_query=0.0005)
    reg.rebuild(builtin_agents={"a": a1}, external_agents={"b": a2})
    best = reg.pick_best_provider("x")
    assert best.provider_agent_name == "Cheap"


def test_enrichment_suggestions_union():
    """If multiple providers offer the same capability with different enrichment
    hints, the registry exposes the union."""
    reg = CapabilityRegistry()
    a1 = FakeAgent("A1", ["cap1"], capability_specs=[{
        "name": "cap1", "enrichment_suggestions": ["sentiment_analysis"],
    }])
    a2 = FakeAgent("A2", ["cap1"], capability_specs=[{
        "name": "cap1", "enrichment_suggestions": ["whale_analysis"],
    }])
    reg.rebuild(builtin_agents={"a": a1}, external_agents={"b": a2})
    hints = reg.get_enrichment_suggestions("cap1")
    assert "sentiment_analysis" in hints
    assert "whale_analysis" in hints


def test_brand_new_capability_name_is_routable():
    """Anyone can invent a capability name and it just works."""
    reg = CapabilityRegistry()
    a = FakeAgent("NftFloorAgent", ["nft_floor_data"])
    reg.rebuild(builtin_agents={}, external_agents={"nft": a})
    assert reg.pick_best_provider("nft_floor_data") is not None
    assert "nft_floor_data" in reg.names()

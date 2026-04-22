"""
NEXUS - Agent Discovery Engine (Pure-LLM, Capability-Registry-Driven)

The routing brain. Reads the LIVE capability registry (built at runtime from
every agent's self-declaration) and asks the LLM to choose which capabilities
should handle a query. Extracts typed identifiers via schema-driven format
handlers — never uppercases contract addresses, never assumes token shapes.

DYNAMISM GUARANTEES:
- No hardcoded capability list (registry is the authority).
- No hardcoded token list; identifiers come from schema-typed extraction.
- No keyword-fallback table. If the LLM is unreachable, routing returns a
  structured `router_unavailable` signal so the user gets an honest error
  rather than a wrong guess.
- Adding a new agent with a new capability requires ZERO edits to this file.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from backend.llm import llm_router
from backend.marketplace.capability_registry import capability_registry, CapabilitySpec
from backend.orchestration.identifier_extractor import extract_for_schema


# ---------- Public classification result ----------

class CapabilitySelection:
    """One capability the LLM chose, with its extracted typed input."""
    def __init__(
        self,
        capability: str,
        provider: CapabilitySpec,
        identifiers: dict[str, Any],
        missing_required: Optional[list[str]] = None,
        suggested_enrichments: Optional[list[str]] = None,
        reasoning: str = "",
    ):
        self.capability = capability
        self.provider = provider
        # Convenience mirrors (used by older call sites)
        self.agent_id = provider.provider_agent_id
        self.agent_name = provider.provider_agent_name
        self.price = provider.price_usdc
        self.reputation = provider.provider_reputation
        self.source = provider.provider_source
        # New-shape fields
        self.identifiers = identifiers
        self.missing_required = missing_required or []
        self.suggested_enrichments = suggested_enrichments or []
        self.reasoning = reasoning


class QueryClassification:
    """
    Structured routing decision returned by classify_query().

    `status`:
      - "routed"              : LLM picked one or more capabilities successfully
      - "no_agent_available"  : LLM understood the query but nothing in the catalog fits
      - "not_applicable"      : LLM decided the query isn't in-scope for this economy
      - "router_unavailable"  : every LLM provider failed; no guessing
    """
    def __init__(
        self,
        status: str,
        selections: list[CapabilitySelection],
        requested_capabilities: list[str],
        missing_capabilities: list[str],
        reasoning: str = "",
        raw_llm: Optional[dict] = None,
    ):
        self.status = status
        self.selections = selections
        self.requested_capabilities = requested_capabilities
        self.missing_capabilities = missing_capabilities
        self.reasoning = reasoning
        self.raw_llm = raw_llm or {}

        # Back-compat fields so older call sites keep working during rollout.
        # Down-stream code should migrate to `selections` + `status`.
        self.query_type = status
        self.confidence = 0.95 if status == "routed" else 0.2
        self.capabilities = list(requested_capabilities)
        # `token` is a convenience — first identifier across all selections.
        self.token = self._first_identifier_value()

    def _first_identifier_value(self) -> str:
        for sel in self.selections:
            for v in sel.identifiers.values():
                if v:
                    return str(v)
        return ""


# ---------- Engine ----------

class DiscoveryEngine:

    # ---- Primary API ----

    async def classify_query(
        self,
        query: str,
        user_enrichment_pref: str = "auto",  # "auto" | "off" | explicit list handled upstream
    ) -> QueryClassification:
        """
        Ask the LLM: which registered capabilities should handle this query?
        Then resolve each pick to a specific provider, extract typed identifiers
        from the query via each capability's input_schema, and optionally append
        author-declared enrichment suggestions.
        """
        specs = capability_registry.all_specs()
        if not specs:
            return QueryClassification(
                status="no_agent_available",
                selections=[], requested_capabilities=[], missing_capabilities=[],
                reasoning="Capability registry is empty — no agents registered.",
            )

        llm_result = await self._llm_route(query, specs)
        if llm_result is None:
            return QueryClassification(
                status="router_unavailable",
                selections=[], requested_capabilities=[], missing_capabilities=[],
                reasoning="LLM routing unavailable and keyword-fallback is intentionally disabled.",
            )

        if not llm_result.get("in_scope", True):
            return QueryClassification(
                status="not_applicable",
                selections=[], requested_capabilities=[], missing_capabilities=[],
                reasoning=llm_result.get("reasoning", ""),
                raw_llm=llm_result,
            )

        picked: list[str] = [c for c in (llm_result.get("capabilities") or [])
                             if isinstance(c, str) and c.strip()]
        if not picked:
            return QueryClassification(
                status="no_agent_available",
                selections=[], requested_capabilities=[], missing_capabilities=[],
                reasoning=llm_result.get("reasoning", "LLM found no matching capability."),
                raw_llm=llm_result,
            )

        # Safety-net post-filter against LLM force-fits. If the router picked
        # capabilities but the query contains ZERO detectable crypto signals
        # (no address, no known ticker, no crypto-context word), treat the
        # pick as a false positive and return `not_applicable`. This catches
        # cases like "what's the new Taylor Swift song mean?" where the LLM
        # latches onto `news_summary` without noticing the query is off-topic.
        if not self._has_crypto_signal(query) and not (llm_result.get("identifier_hints") or {}):
            return QueryClassification(
                status="not_applicable",
                selections=[], requested_capabilities=[], missing_capabilities=[],
                reasoning=(
                    "Query has no detectable crypto signal (no token symbol, address, "
                    "or crypto-context keyword). The LLM's capability pick was treated "
                    "as a force-fit and rejected."
                ),
                raw_llm=llm_result,
            )

        # Optional enrichment: two sources.
        #  (1) Per-capability `enrichment_suggestions` declared by the agent author.
        #  (2) Implicit platform policy: if ANY analysis-ish capability was
        #      picked and a `quality_audit` provider exists, auto-append it.
        #      This preserves the original "AuditAgent on every analysis" UX
        #      without requiring every external agent to declare it explicitly.
        if user_enrichment_pref != "off":
            enrichments: list[str] = []
            for cap_name in list(picked):
                for hint in capability_registry.get_enrichment_suggestions(cap_name):
                    if hint not in picked and hint not in enrichments:
                        if capability_registry.providers_for(hint):
                            enrichments.append(hint)
            # Auto-include quality_audit as a platform-level policy.
            if (
                "quality_audit" not in picked
                and "quality_audit" not in enrichments
                and capability_registry.providers_for("quality_audit")
            ):
                enrichments.append("quality_audit")
            picked.extend(enrichments)

        # Resolve each pick to a provider + extract typed identifiers.
        identifier_hints = llm_result.get("identifier_hints") or {}
        selections: list[CapabilitySelection] = []
        missing: list[str] = []
        picked_providers: set[str] = set()

        for cap_name in picked:
            provider = capability_registry.pick_best_provider(cap_name)
            if provider is None:
                missing.append(cap_name)
                continue
            if provider.provider_agent_name in picked_providers:
                # Avoid paying the same agent twice in one query.
                continue
            picked_providers.add(provider.provider_agent_name)

            extracted, missing_req = extract_for_schema(
                text=query,
                schema=provider.input_schema,
                hints=identifier_hints,
            )
            selections.append(CapabilitySelection(
                capability=cap_name,
                provider=provider,
                identifiers=extracted,
                missing_required=missing_req,
                suggested_enrichments=capability_registry.get_enrichment_suggestions(cap_name),
                reasoning=llm_result.get("reasoning", ""),
            ))

        return QueryClassification(
            status="routed" if selections else "no_agent_available",
            selections=selections,
            requested_capabilities=picked,
            missing_capabilities=missing,
            reasoning=llm_result.get("reasoning", ""),
            raw_llm=llm_result,
        )

    def build_execution_plan(self, classification: QueryClassification) -> dict:
        """Public structure surfaced in reports + the /api/query response."""
        return {
            "status": classification.status,
            "confidence": classification.confidence,
            "capabilities_needed": classification.requested_capabilities,
            "agents_selected": [
                {
                    "capability": s.capability,
                    "agent": s.agent_name,
                    "agent_id": s.agent_id,
                    "price": s.price,
                    "reputation": s.reputation,
                    "source": s.source,
                    "identifiers": s.identifiers,
                    "missing_required_inputs": s.missing_required,
                    "suggested_enrichments": s.suggested_enrichments,
                }
                for s in classification.selections
            ],
            "missing_capabilities": classification.missing_capabilities,
            "marketplace_hint": (
                f"No agent found for: {', '.join(classification.missing_capabilities)}. "
                f"Register one at POST /api/marketplace/register"
                if classification.missing_capabilities else None
            ),
            "estimated_cost": sum(s.price for s in classification.selections),
            "complete": (
                classification.status == "routed"
                and not classification.missing_capabilities
            ),
            "reasoning": classification.reasoning[:200] if classification.reasoning else "",
        }

    # ---- Crypto-signal heuristic (post-LLM safety net) ----
    # A small, conservative list of crypto-indicator keywords and shapes.
    # Used ONLY as a guard against LLM force-fits — not as primary routing.
    # Primary routing is still the LLM. This just catches obvious off-topic
    # queries the LLM occasionally hallucinates into a capability.
    _CRYPTO_CONTEXT_WORDS: frozenset = frozenset({
        # scope / system nouns
        "crypto", "cryptocurrency", "token", "coin", "coins", "blockchain",
        "defi", "nft", "nfts", "dao", "onchain", "on-chain", "airdrop",
        "staking", "staked", "yield", "tvl", "apy", "apr", "liquidity",
        "dex", "amm", "pool", "lp", "lending", "borrow",
        # trading / market
        "bullish", "bearish", "whale", "sentiment", "pump", "dump", "moon",
        "hodl", "trade", "trading", "market cap", "marketcap",
        # safety / ops
        "rug", "rugpull", "honeypot", "scam", "audit", "exploit",
        # well-known chains / L1s
        "bitcoin", "ethereum", "solana", "kite", "aero", "arbitrum",
        "polygon", "avalanche", "optimism", "base", "bsc", "bnb",
        # common base tickers — keep short list; not an exhaustive registry
        "btc", "eth", "sol", "usdc", "usdt", "bnb", "aave", "uni", "pepe",
        "matic", "arb", "op", "link",
        # protocol addressing
        "contract address", "token address", "passport",
    })

    _EVM_ADDRESS_RE = __import__("re").compile(r"0x[0-9a-fA-F]{40}")
    _SOLANA_ADDRESS_RE = __import__("re").compile(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b")

    def _has_crypto_signal(self, query: str) -> bool:
        """Return True if the query carries any recognizable crypto signal.

        Signals (any one is sufficient):
          • a 0x-prefixed EVM address (42 hex)
          • a Solana/base58-shaped address (32-44 chars)
          • any word from `_CRYPTO_CONTEXT_WORDS`
          • any example_query keyword a registered capability declared

        Deliberately permissive — we only want to catch obviously-non-crypto
        queries like "Taylor Swift song meaning". False negatives here would
        trigger wrongful `not_applicable` rejections; false positives just
        let the LLM's routing stand, which is the default behavior.
        """
        if not query:
            return False
        q = query.lower()
        words = {w.strip(".,!?;:'\"()[]") for w in q.split()}

        if self._CRYPTO_CONTEXT_WORDS & words:
            return True

        # Multi-word phrases like "market cap" / "contract address".
        for phrase in self._CRYPTO_CONTEXT_WORDS:
            if " " in phrase and phrase in q:
                return True

        if self._EVM_ADDRESS_RE.search(query):
            return True
        # Solana match is permissive; restrict to strings that are NOT
        # regular English words.
        for m in self._SOLANA_ADDRESS_RE.finditer(query):
            candidate = m.group(0)
            if len(candidate) >= 32 and not candidate.isalpha():
                return True

        # Capability-declared keywords (author opt-in: if an agent declared
        # a keyword like "goldrush", a query mentioning "goldrush" is a
        # legitimate crypto signal for that agent).
        try:
            for spec in capability_registry.all_specs():
                for kw in spec.keywords or []:
                    if kw and kw.lower() in q:
                        return True
        except Exception:
            pass

        return False

    # ---- Back-compat shim ----
    # Older call sites used `discover_agents_for_capabilities(caps, builtin_agents)`.
    # Classification now does resolution internally, but keep the shim for tests.
    def discover_agents_for_capabilities(
        self, capabilities: list[str], builtin_agents: dict,
    ) -> tuple[list[CapabilitySelection], list[str]]:
        selections: list[CapabilitySelection] = []
        missing: list[str] = []
        for cap in capabilities:
            provider = capability_registry.pick_best_provider(cap)
            if provider is None:
                missing.append(cap)
                continue
            selections.append(CapabilitySelection(
                capability=cap,
                provider=provider,
                identifiers={},
            ))
        return selections, missing

    # ---- Internal LLM routing ----

    async def _llm_route(
        self, query: str, specs: list[CapabilitySpec],
    ) -> Optional[dict]:
        """
        Ask the LLM in one call:
          - is this query in scope for the agent economy?
          - if yes, pick capabilities from the live registry
          - provide identifier hints (pre-filled values) if they're obvious

        Returns parsed dict on success, None if no LLM provider responded.
        """
        # Summarize the registry for the prompt (deduped by capability name).
        by_name: dict[str, list[CapabilitySpec]] = {}
        for s in specs:
            by_name.setdefault(s.name, []).append(s)

        catalog_lines: list[str] = []
        for name, provs in sorted(by_name.items()):
            primary = provs[0]  # one description is enough
            providers_str = ", ".join(
                f"{p.provider_agent_name} (rep {p.provider_reputation}, ${p.price_usdc})"
                for p in provs
            )
            input_fields = list((primary.input_schema or {}).get("properties", {}).keys())
            examples_str = "; ".join(primary.example_queries[:2]) or "-"
            catalog_lines.append(
                f"- {name}: {primary.description or '(no description)'}\n"
                f"    providers: {providers_str}\n"
                f"    expects: {', '.join(input_fields) or '(no structured input)'}\n"
                f"    examples: {examples_str}"
            )

        capability_names = sorted(by_name.keys())
        catalog_str = "\n".join(catalog_lines)

        prompt = (
            f'You are the router for NEXUS, a capability marketplace of AI agents.\n\n'
            f'USER QUERY:\n"""{query}"""\n\n'
            f"LIVE CAPABILITY REGISTRY (live agents and what they offer):\n"
            f"{catalog_str}\n\n"
            f"VALID CAPABILITY NAMES (choose from this exact set): {capability_names}\n\n"
            f"INSTRUCTIONS:\n"
            f"1. Decide: is this query in scope for any capability in the registry?\n"
            f"2. If yes, pick the MINIMAL set of capabilities that directly addresses the query.\n"
            f"3. If you can see an identifier in the query (token symbol, contract address,\n"
            f"   URL, protocol name, etc.), add it to `identifier_hints`. Preserve case —\n"
            f"   never uppercase a 0x address. If nothing obvious, return {{}}.\n"
            f"4. If NO capability in the registry actually fits, return capabilities: [] —\n"
            f"   never force-fit. An honest 'no agent available' is better than wrong output.\n\n"
            f"STRICT RULES:\n"
            f"- Only use capability names from the valid set above.\n"
            f"- Never invent a capability name.\n"
            f"- For `in_scope`: mark false UNLESS the query is clearly about\n"
            f"  cryptocurrency, tokens, blockchain, DeFi, NFTs, or a specific\n"
            f"  on-chain asset. When in doubt, mark false. Every one of the\n"
            f"  following examples MUST be classified in_scope=false, capabilities=[]:\n"
            f"    • 'what does the new Taylor Swift song mean' → false (pop music)\n"
            f"    • 'how's the weather in Tokyo' → false (weather)\n"
            f"    • 'what is the capital of France' → false (geography)\n"
            f"    • 'recipe for chocolate cake' → false (food)\n"
            f"    • 'news about the election' → false (general news, NOT crypto)\n"
            f"    • 'explain quantum computing' → false (science, not crypto)\n"
            f"    • 'best football players 2026' → false (sports)\n"
            f"- Do NOT pick `news_summary`, `sentiment_analysis`, or `data_analysis`\n"
            f"  for news/sentiment about NON-crypto topics. Those capabilities are\n"
            f"  scoped to crypto queries only.\n"
            f"- Only pick capabilities when the query contains at least ONE of:\n"
            f"  a token symbol (e.g. BTC, ETH, SOL, AAVE, PEPE), a 0x contract\n"
            f"  address, a Solana base58 address, OR an explicit crypto keyword\n"
            f"  (defi, nft, yield, tvl, apy, liquidity, dex, rug, honeypot,\n"
            f"  whale, blockchain, crypto, token, staking, airdrop, etc.).\n\n"
            f"Reply with ONLY a single JSON object, no markdown, no prose:\n"
            f'{{"in_scope": true, "capabilities": ["cap_name", ...], '
            f'"identifier_hints": {{"identifier":"..."}}, "reasoning":"short why"}}\n'
        )

        try:
            raw = await llm_router.generate(prompt=prompt, max_tokens=260)
        except Exception as e:
            print(f"[Discovery] LLM call error: {e}")
            return None

        if not raw or (isinstance(raw, str) and raw.startswith("[LLM unavailable")):
            return None

        parsed = self._parse_json(raw)
        if parsed is None:
            print(f"[Discovery] LLM returned unparseable output: {str(raw)[:120]}")
            return None

        # Normalize keys/values.
        caps = parsed.get("capabilities")
        if not isinstance(caps, list):
            caps = []
        caps = [str(c).strip() for c in caps if isinstance(c, str) and c.strip()]

        # Filter to valid names only. Silent-drop unknown capabilities (don't
        # invent); missing ones surface as `missing_capabilities` instead.
        valid = set(capability_names)
        caps = [c for c in caps if c in valid]

        hints = parsed.get("identifier_hints")
        if not isinstance(hints, dict):
            hints = {}

        return {
            "in_scope": bool(parsed.get("in_scope", True)),
            "capabilities": caps,
            "identifier_hints": hints,
            "reasoning": str(parsed.get("reasoning") or "")[:300],
        }

    @staticmethod
    def _parse_json(raw: str) -> Optional[dict]:
        if not raw:
            return None
        text = raw.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)
        first = text.find("{")
        last = text.rfind("}")
        if first < 0 or last <= first:
            return None
        candidate = text[first:last + 1]
        try:
            return json.loads(candidate)
        except Exception:
            try:
                return json.loads(candidate.replace("'", '"'))
            except Exception:
                return None


# ---------------------------------------------------------------------------
# Built-in agents registry shim (kept for startup bootstrapping).
# The capability_registry is rebuilt from this + marketplace agents on every
# registration event.
# ---------------------------------------------------------------------------

_builtin_agents_registry: Optional[dict] = None


def register_builtin_agents(builtin_agents: dict) -> None:
    """Called once from main.py startup. Triggers initial capability-registry build."""
    global _builtin_agents_registry
    _builtin_agents_registry = builtin_agents
    # Build the initial capability index. marketplace.external_agents may be
    # empty at this point; rebuild is called again after marketplace hydration.
    try:
        from backend.marketplace.registry import marketplace
        capability_registry.rebuild(builtin_agents, marketplace.external_agents)
    except Exception as e:
        print(f"[Discovery] initial capability registry build failed: {e}")


def rebuild_capability_registry() -> int:
    """Called after every marketplace.register/unregister. Re-indexes everything."""
    from backend.marketplace.registry import marketplace
    return capability_registry.rebuild(
        _builtin_agents_registry or {},
        marketplace.external_agents,
    )


# Global singleton
discovery_engine = DiscoveryEngine()

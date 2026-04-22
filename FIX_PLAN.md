# NEXUS — Dynamic, Chain-First Fix Plan

> Rewritten 2026-04-17 under the **Dynamism Mandate**: no hardcoded agents, capabilities, tokens, chains, query shapes, or report fields. Anyone registers any agent with any capability; any user asks any question; the system routes, pays, audits, and reports with zero code change. Kite chain is the authoritative source for reputation, earnings, and economy state.

---

## 1. The Dynamism Mandate

The backend and frontend must **never** assume:

| Assumption to eliminate | Where it lives today | Why it's wrong |
|---|---|---|
| A specific agent name (`Nexus-DataAgent-v1`, `GoPlus-Security-Agent-v1`) | discovery prompts, report compilation, tests | New agents should be first-class |
| A fixed set of capabilities (`data_collection`, `sentiment_analysis`, `token_security`) | discovery fallback, enrichment lists | Agents should be able to declare any capability |
| A "built-in vs external" hierarchy | payment flow, reputation handling, leaderboard | All agents are marketplace participants |
| Token shapes (3-10 char symbol OR `0x…42 chars`) | `.upper()` calls, regex in agents | Breaks for Solana, Cosmos, contract-addresses with checksum, future chains |
| A fixed list of example queries on the frontend | `PRESET_QUERIES` in dashboard | New agents can't surface their example queries |
| A report always has `verdict`, `confidence`, `score`, `summary` | `_compile_full_report` | These fields exist only if an agent produced them |
| A fixed set of "known tokens" (KITE, BTC, ETH…) | `discovery.py` fallback | Should come from chain/registry, not code |
| One chain (Kite testnet) for data reads | `whale_tracker`, `security-agent` | Chains are metadata, not constants |

Everything must be derived at runtime from four sources:

1. **Agent self-declarations** at registration — the agent is the authority on its own capabilities, schemas, keywords, example queries, supported chains, and enrichment suggestions.
2. **On-chain state** — `AgentRegistry`, `ReputationTracker`, `PaymentRouter`, `GovernanceRules` contracts on Kite.
3. **Live LLM classification** over the current catalog — no keyword fallback tables.
4. **Explicit user overrides** — optional request flags (`enrichments`, `chain`, `budget_override`).

---

## 2. Defect inventory (dynamic lens)

Each issue reframed so the fix works for any future agent:

| # | Defect | Hardcoding hidden inside | Dynamic fix direction |
|---|---|---|---|
| **D-1** | Security agent silently failed; `$0.0002` lost; `sections={}` | `.upper()` on tokens (discovery.py:314), case-sensitive `0x` check (security-agent:272), agent-specific `if "error" in result: continue` (report_agent.py:265) | Schema-driven identifier extraction; universal invocation envelope; no agent-specific error handling |
| **D-2** | Failures are invisible to WebSocket, audit trail, report | Silent `continue` swallowing arbitrary agent errors | Every invocation (success OR failure OR timeout) emits the same envelope + WS event |
| **D-3** | Payment debited before agent probed; no refund semantics | No probe step; no `FAILED` payment state | Generic pre-flight probe (`GET callback_url/health`) + generic `PaymentStatus` enum with `FAILED_DOWNSTREAM` |
| **D-4** | DataAgent/AnalystAgent skipped on Q1/Q2 → `verdict=N/A`, `score=0` | Discovery returns exactly 1 agent per capability; report expects hardcoded fields | Enrichment suggestions declared by agents themselves; report is schema-driven (no implicit `verdict`) |
| **D-5** | `/api/reputation` omits external agents | `ALL_AGENTS` = 5 built-ins | Leaderboard reads chain for every passport in the catalog |
| **D-6** | SQLite is authority for earnings/stats/jobs | in-memory `BaseAgent` state + SQLite | `chain_reader` reads `ReputationTracker` + `PaymentRouter`; SQLite is history-only cache |
| **D-7** | Whale tracker ignores the agent payment graph | `whale_tracker.py` uses only Helius/WhaleAlert/DeFiLlama | Whale feed includes `PaymentRouter.payments[]` top-by-amount, tagged `source=kite_onchain` |
| **D-8** | Mandate status race (active in response, completed in `/api/mandates`) | Status flipped after response serialized | Complete mandate synchronously inside `_compile_full_report` before serialization |

All 8 collapse into the same architectural shift: stop hardcoding, move authority to chain + agent-self-declarations + LLM.

---

## 3. Architectural Changes

### 3.1 Capability Registry (new)

A runtime-built index populated at registration time and rebuilt on every change (`registry_changed` WebSocket event).

**Schema** — every registered agent declares:

```jsonc
{
  "name": "AnyAgentName",
  "description": "...",
  "capabilities": [
    {
      "name": "any_capability_string",               // author chooses; no enum
      "description": "what it does",
      "input_schema": {                              // JSONSchema draft 2020-12
        "type": "object",
        "properties": {
          "identifier": { "type": "string", "format": "evm_address" },
          "chain":      { "type": "string", "enum": ["ETH","BSC","SOL","KITE"] }
        },
        "required": ["identifier"]
      },
      "output_schema": { "type": "object", "properties": { "risk_level": {"type":"string"}, "findings": {"type":"array"} } },
      "enrichment_suggestions": ["any_other_capability_name"],   // author's hints; not enforced
      "example_queries": ["sample user inputs"],
      "keywords": ["words that hint at this capability"],
      "timeout_ms": 15000,
      "price_usdc": 0.0002
    }
  ],
  "callback_url": "http://host:port/invoke",
  "owner_address": "0x..."
}
```

The registry exposes `GET /api/capabilities` returning the flat list, and the Discovery engine prompts the LLM with this live list on every query. **No enum, no allowlist, no registered-capability filter on the backend.** Any new capability string becomes routable the moment it registers.

### 3.2 Universal Invocation Envelope

Every agent call — built-in, marketplace, future-type — goes through one orchestration wrapper.

```python
# backend/orchestration/envelope.py
class InvocationRequest(BaseModel):
    request_id: str
    mandate_id: str
    agent_id: str            # any agent_id from the catalog
    capability: str          # any capability from the registry
    input: dict              # validated against capability.input_schema
    payment_tx_hash: str | None
    timeout_ms: int
    emitted_at: datetime

class InvocationResult(BaseModel):
    request_id: str
    agent_id: str
    capability: str
    status: Literal["success", "partial", "failed", "timeout"]
    output: dict | None
    error_code: str | None       # e.g. "invalid_input", "upstream_5xx", "unreachable"
    error_message: str | None
    duration_ms: float
    payment_tx_hash: str | None
```

The orchestrator:

1. Validates `input` against `capability.input_schema` — fails fast with `status="failed"` + `error_code="invalid_input"`, no payment fires.
2. Probes the target (§3.5) — if unreachable, returns `status="failed"` + `error_code="unreachable"`, no payment fires.
3. Pays.
4. Invokes (HTTP for marketplace, direct call for in-process).
5. Returns the envelope.

**Report sections are always populated with these envelopes.** No branch-specific "is built-in" / "is marketplace" / "was successful" logic in downstream code.

### 3.3 Schema-Driven Identifier Extraction (replaces `.upper()`)

New module `backend/orchestration/identifier_extractor.py` — a pluggable set of format handlers. A handler advertises a format name + predicate + normalizer:

```python
@register_format("evm_address")
class EvmAddress(FormatHandler):
    regex = re.compile(r"0x[0-9a-fA-F]{40}")
    def normalize(self, raw: str) -> str: return raw        # preserve checksum
    def detect(self, text: str) -> Optional[str]: ...

@register_format("solana_address")
class SolanaAddress(FormatHandler):
    regex = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b")
    ...

@register_format("erc20_symbol")
class Erc20Symbol(FormatHandler):
    # only returns a match if the string is NOT already an evm_address
    ...

@register_format("cosmos_bech32"), @register_format("url"), @register_format("protocol_slug")
```

Discovery resolves each capability's `input_schema.properties.*.format` to a handler and extracts the typed value from the raw user query. Unknown formats degrade to `"string"` (pass raw text; let the agent parse). **No global token `.upper()` anywhere.** Format handlers are discoverable via entry-points, so third parties add formats without editing core code.

### 3.4 Pure-LLM Discovery with Live Catalog (no keyword fallback)

`backend/marketplace/discovery.py` rewritten around one prompt:

```
You are the NEXUS router. Given the user's query and the live capability registry below,
return a JSON object:
{
  "selected": [
    {
      "capability": "<exact name from registry>",
      "identifiers": {"<field_from_input_schema>": "<extracted value>"},
      "suggested_enrichments": ["<cap>", ...],   // from that capability's own enrichment_suggestions
      "confidence": 0.0-1.0
    }
  ],
  "router_note": "optional short reason"
}

Registry: <auto-injected JSON of all capabilities with their schemas, descriptions, enrichment_suggestions>
Query: <user input>
```

If the LLM is unavailable: return `{"status":"router_unavailable"}` to the caller — do NOT fall back to a hardcoded keyword table. The "keyword" field of each capability is shown *to the LLM* as a hint, but the backend itself does no keyword matching.

### 3.5 Generic Probe + Payment-State Machine

`backend/marketplace/probe.py`:

```python
async def probe(agent: AgentRecord) -> ProbeResult:
    """Generic reachability check. Works for any agent with a callback_url.
       Cache 30s per agent_id. No agent-specific logic."""
    url = agent.callback_url.rsplit("/invoke", 1)[0] + "/health"
    try:
        r = await httpx.get(url, timeout=2.0)
        return ProbeResult(reachable=r.status_code == 200, ms=r.elapsed, code=r.status_code)
    except (TimeoutError, ConnectError, httpx.HTTPError) as e:
        return ProbeResult(reachable=False, error=str(e))
```

For in-process built-ins, probe is a no-op `reachable=True`.

`PaymentStatus` enum extended with:

- `BLOCKED_UNREACHABLE` — probe failed; no chain tx ever fires
- `FAILED_DOWNSTREAM` — payment succeeded but agent returned envelope with `status="failed"` or `"timeout"`
- `SUCCEEDED` — payment + envelope success

Mandate `payment_log[]` records whichever status applies. `/api/mandates` exposes the full log.

### 3.6 Dynamic Enrichment (no backend-defined list)

Each capability's `enrichment_suggestions` field (author-declared) is what drives enrichment. The orchestrator's rule:

```python
for cap in initially_selected:
    cap_meta = capability_registry.get(cap)
    for hint in cap_meta.enrichment_suggestions:
        if hint in capability_registry and request.enrichments in ("auto", list_containing(hint)):
            queue_enrichment(hint)
```

User can override per request: `{"query": "...", "enrichments": "off"}` or `{"query": "...", "enrichments": ["any_cap_name"]}`.

No `ENRICHMENT_CAPABILITIES` constant anywhere. If an analytics agent wants to opt into being suggested, it says so in its own `enrichment_suggestions`.

### 3.7 Dynamic Report Compilation

`ReportAgent._compile_full_report` becomes schema-agnostic:

```python
async def _compile(query, envelopes, mandate, audit_trail, economy_stats):
    sections = {env.capability: env.model_dump() for env in envelopes}   # always populated, success or fail
    # LLM summary takes whatever envelopes contain — prompt adapts to whatever fields are present
    summary = await llm_router.summarize(query, envelopes)
    # Only add fields that an envelope's output actually carries:
    output_fields = collect_output_fields_across(envelopes)   # e.g. if any capability returned "risk_level", include it
    return Report(
        report_id=..., query=query, sections=sections, summary=summary,
        classification=..., verified_intent=mandate_summary,
        audit_trail=audit_trail, economy_stats=economy_stats,
        output_fields=output_fields,   # dict that only has keys some agent produced
    )
```

No `verdict: "N/A"` anymore — if no agent produced a verdict, the field is absent. Frontend renders fields that exist. An agent that invents a new field (`nft_floor_usd`) surfaces automatically.

### 3.8 Chain-First State

New `backend/blockchain/chain_reader.py`:

```python
async def get_reputation_record(passport_id: bytes) -> ReputationRecord
async def get_bulk_reputation(passport_ids: list[bytes]) -> dict[bytes, ReputationRecord]
async def get_payment_totals(passport_id: bytes) -> PaymentTotals
async def get_bulk_payment_totals(passport_ids: list[bytes]) -> dict[...]
async def get_recent_payments(limit: int = 200) -> list[OnchainPayment]
async def get_payment_count() -> int
async def get_all_registered_agents() -> list[AgentOnchainRecord]   # AgentRegistry sweep
```

Every method takes passport IDs, not agent names. Works for any current or future agent.

Endpoint rewrites:
- `/api/reputation` — passport loop via `chain_reader`, sorted by score. SQLite supplies only the `history` array.
- `/api/stats` — `PaymentRouter.getPaymentCount()` + sum of `getTotalEarned` across all agents. SQLite aggregates demoted to `legacy_cache_*` fields.
- `/api/agents` — merges AgentRegistry sweep with catalog metadata; drift flag when mismatched.

Acceptance: `mv nexus.db nexus.db.bak` → all GETs still serve correct data (only `history` arrays empty).

### 3.9 Dynamic Frontend

- `PRESET_QUERIES` removed. New component `DynamicQuerySuggestions` reads `/api/capabilities` and samples `example_queries` across capabilities, weighted by provider reputation.
- Agents panel reads `/api/agents` and renders whatever fields exist; no hardcoded agent-name display logic.
- Register-agent form uses `POST /api/marketplace/register` with a JSON-schema-driven form (new capabilities, new fields, all accepted).
- WebSocket `registry_changed` event triggers suggestion/agent-list re-fetch.
- Report display iterates `report.sections` instead of looking for `sections.data_agent` etc. Each section renders a generic `EnvelopeCard` keyed by capability name.

### 3.10 Governance-Driven Constants

Values like "mandate TTL", "budget multiplier", "min reputation" are not hardcoded — they come from `GovernanceRules` contract reads (already exists) with sane defaults. Add endpoint `GET /api/governance` that returns the live rule set.

---

## 4. Phased Delivery

Each PR is independently deployable, dynamic, and ships with synthetic-agent tests (no real-agent dependency).

### PR-1 — Universal Envelope + Schema-Driven Extraction

Addresses D-1, D-2, address-normalization. Makes the silent-failure and case-sensitivity defects disappear as side-effects of the architectural shift.

**Changes:**
- New: `backend/orchestration/envelope.py` (InvocationRequest, InvocationResult models)
- New: `backend/orchestration/identifier_extractor.py` (pluggable format registry)
- Rewrite: `backend/agents/report_agent.py:220-310` — all agent calls pass through `orchestrator.invoke(request)`, which returns an envelope. Failure and success handled uniformly.
- Delete: every `.upper()` on query/token; replaced by schema-driven extraction
- WebSocket: emit `work_completed` with `status` field (success/failed/timeout) for every invocation
- Agent contract (marketplace): each agent returns `{status, output, error_code, error_message}` — standard envelope. Backward compat: if an old agent returns raw `{error: "..."}`, orchestrator wraps it.

**Acceptance:**
- Register an ephemeral `TestAgent` that always returns `{"error": "boom"}`. Report contains `sections[test_capability].status == "failed"`. No `.db` writes for that payment.
- Q3 rerun: Security agent receives the 0x address in its native case, succeeds, report populated.
- Register an agent with capability `foobar_xyz` declaring `input_schema: {identifier: {format: "url"}}`. Submit `"Check https://example.com"`. Agent receives `identifier=https://example.com`.

### PR-2 — Generic Probe + Payment-State Machine

Addresses D-3.

**Changes:**
- New: `backend/marketplace/probe.py`
- `BaseAgent.make_payment` calls `probe()` first; returns `Transaction(status=BLOCKED_UNREACHABLE)` on failure without chain call
- Mandate `payment_log` records the new states; `/api/mandates` serializes them
- Frontend Activity panel renders `BLOCKED_UNREACHABLE` and `FAILED_DOWNSTREAM` with distinct icons
- Contract-side refund is not needed — we simply don't fire chain tx when probe fails

**Acceptance:**
- Kill any agent's port. Submit a query that would route to it. Mandate log shows one `BLOCKED_UNREACHABLE` entry. Zero on-chain tx for that payment. Other agents still execute.
- Make an agent return 500 on `/invoke`. Log shows `FAILED_DOWNSTREAM` with the payment tx hash. Reputation decremented via `ReputationTracker.recordFailure`.

### PR-3 — Capability Registry + Pure-LLM Discovery

Addresses D-4's root (hardcoded capabilities), removes keyword-fallback table.

**Changes:**
- New: `backend/marketplace/capability_registry.py` (in-memory, rebuilt on register/unregister, persisted to SQLite for warm starts)
- New: `GET /api/capabilities` endpoint
- Rewrite: `backend/marketplace/discovery.py` — prompt-based routing using the live registry; remove `KNOWN_TOKENS`, `KNOWN_CRYPTO_CONTEXT`, keyword-fallback function
- Classification result shape: `{selected: [{capability, identifiers, suggested_enrichments}], router_note}`. No `token` top-level field (identifiers are per-capability now).
- `/api/marketplace/register` validates that each capability includes the required self-description fields; otherwise rejects

**Acceptance:**
- Register `NftFloorAgent` with capability `nft_floor_data` and example_queries `["OpenSea floor for BAYC"]`. Submit that exact query. Agent gets routed. No backend file changed to enable this.
- Turn LLM key invalid. Query returns HTTP 503 with `{"error": "router_unavailable"}` — no fallback guessing.
- Frontend's `/api/capabilities` response shows the newly-registered capability immediately.

### PR-4 — Chain as Source of Truth

Addresses D-5, D-6.

**Changes:**
- New: `backend/blockchain/chain_reader.py` with batched view-function reads (parallel `asyncio.gather`, 5-second block cache)
- Rewrite `/api/reputation`, `/api/stats`, `/api/agents` to read from `chain_reader`
- SQLite `reputation_events`, `transactions` tables become append-only history only; no reads for live totals
- Drift monitor runs every 60s — compares in-memory BaseAgent.reputation_score with chain value; WebSocket `reputation_drift_detected` on mismatch (diagnostic only, non-fatal)
- Optional follow-up (not blocking): AgentRegistry.getAllAgents() bulk view function — if gas is fine on Kite testnet, deploy and use; else keep N+1 view reads (still free)

**Acceptance:**
- `mv backend/nexus.db backend/nexus.db.bak`; restart backend. `/api/reputation`, `/api/agents`, `/api/stats` all return correct live data (history arrays empty as expected).
- External agent reputation changes on-chain via `ReputationTracker.recordSuccess`. `/api/reputation` reflects the change within 5 seconds (cache TTL).
- Restore SQLite. Drift monitor fires no false positives.

### PR-5 — Dynamic Enrichment

Addresses D-4's "why was analyst skipped" side.

**Changes:**
- `capability.enrichment_suggestions` already present in PR-3 metadata; honor it at discovery time
- Request flag: `POST /api/query {"query": "...", "enrichments": "auto" | "off" | ["cap1","cap2"]}`
- Discovery merges user-explicit enrichments with author-declared hints, de-duplicates, budget-checks via the Verified Intent mandate
- No hardcoded enrichment list in any file (`git grep -i enrichment_capabilities` returns empty)

**Acceptance:**
- Built-in agents declare `enrichment_suggestions: ["sentiment_analysis"]` on their data-collection capability. Q1 rerun: enrichment fires, AnalystAgent included, `output_fields.verdict` present.
- `enrichments=off` flag: only specialist runs, report sections contain only that capability's envelope.
- Register a new `RiskAnalystAgent` and set its `enrichment_suggestions=["token_security"]`. After registration, queries hitting the security agent auto-include the new risk analyst. No backend code change.

### PR-6 — Dynamic Frontend

Addresses UI hardcoding.

**Changes:**
- Delete `PRESET_QUERIES` const in `frontend/src/app/dashboard/page.tsx`. Replace with `<DynamicQuerySuggestions />` reading `/api/capabilities` + reputation-weighted sampling
- `ReportDisplay` iterates `report.sections` dict with a generic `EnvelopeCard`; no hardcoded `data_agent`/`analyst_agent`/etc. keys
- `MarketplaceBrowser` register-form builds fields from `/api/marketplace/register` schema; capability list is a free-text multi-input, not a dropdown
- WebSocket `registry_changed` and `reputation_drift_detected` hooks wired into the UI for live updates
- Agent leaderboard reads full `/api/reputation` list (now includes externals post-PR-4)

**Acceptance:**
- Register a brand-new agent via the UI itself. Suggestions update within 2 seconds (WebSocket push). Agent leaderboard shows the new agent at score 50.
- Submit a query using an example query from the new agent. Report renders correctly without any frontend code change.

### PR-7 — Mandate Consistency + Drift Monitor

Addresses D-8 and cross-cutting observability.

**Changes:**
- `report_agent._compile_full_report` calls `mandate_manager.complete(mandate_id)` BEFORE serializing `verified_intent` into the response
- New test: submit query, assert `response.verified_intent.status == /api/mandates/{id}.status`
- Background drift monitor (from PR-4) extended to also reconcile mandate states vs chain audit trail

**Acceptance:**
- Automated test `test_mandate_status_consistency.py` passes
- Drift monitor emits WebSocket events for any detected inconsistency; no false positives in a 10-minute idle run

### PR-8 (optional, follow-up) — Contract Helpers

Only if Kite testnet gas is negligible and redeploy is acceptable. Deploy bulk-view-function helpers:
- `AgentRegistry.getAllAgents() → AgentRecord[]`
- `ReputationTracker.getBulkRecords(bytes32[]) → Record[]`
- `PaymentRouter.getRecentPayments(uint256) → Payment[]`

Purely a performance optimization for `chain_reader`. Not required for correctness.

---

## 5. Test Strategy — Synthetic Agents Only

Every test registers an ephemeral agent. No test imports a specific built-in agent name or capability.

```python
# backend/tests/helpers.py
@asynccontextmanager
async def temp_agent(capabilities: list[dict], behavior: Callable = ok_response):
    server = SyntheticAgentServer(behavior)
    await server.start()
    try:
        agent_id = await marketplace.register({
            "name": f"SyntheticAgent-{uuid4().hex[:8]}",
            "capabilities": capabilities,
            "callback_url": server.url,
            "owner_address": TEST_WALLET,
        })
        yield agent_id
    finally:
        await marketplace.unregister(agent_id)
        await server.stop()
```

**Test matrix:**

| Test | What it proves |
|---|---|
| `test_arbitrary_capability_routes.py` | Register `capability="x_y_z_never_seen"`; query with the agent's example query routes to it |
| `test_schema_driven_extraction.py` | Capability with `input_schema.identifier.format="url"` receives a URL extracted from the query |
| `test_envelope_failure.py` | Agent returns `{"error":"boom"}`; report sections contain envelope with `status="failed"` |
| `test_probe_prevents_payment.py` | Kill the agent's server; no chain tx; mandate log shows `BLOCKED_UNREACHABLE` |
| `test_chain_as_source.py` | Move SQLite aside; all GETs still correct |
| `test_enrichment_hint.py` | Agent A declares `enrichment_suggestions=["capB"]`; Agent B registers; query hitting A also invokes B |
| `test_router_unavailable.py` | Kill LLM key; `/api/query` returns structured 503; no hardcoded-fallback match |
| `test_no_hardcoded_constants.py` | Static analysis: `grep -R "ENRICHMENT_CAPABILITIES\|KNOWN_TOKENS\|PRESET_QUERIES" backend/ frontend/src/` returns empty |
| `test_mandate_consistency.py` | Response + `/api/mandates` agree on status |

---

## 6. What is NOT being made dynamic (and why)

- **Smart-contract addresses** (`AgentRegistry`, `ReputationTracker`, `PaymentRouter`, `GovernanceRules`) are constants per deployment, loaded from `.env`. They are the trust anchor. Dynamic here = insecure.
- **x402 protocol version**: `x402Version: 1` is a fixed protocol constant until a new version ships.
- **Kite chain ID `2368`**: part of the signed-mandate payload — changing at runtime would invalidate signatures.
- **Free LLM router order (Groq → Gemini → Ollama)**: an operational fallback chain; the order is itself a tunable in `.env`, not hardcoded.

These are explicitly *not* dynamism-mandate violations — they are the minimum trust anchors any agent economy needs.

---

## 7. Rollout and Risk

| PR | Estimated LoC | Backward-compat risk | Mitigation |
|---|---|---|---|
| PR-1 | ~350 | Medium — envelope shape differs from today's raw results | Orchestrator auto-wraps legacy shapes; feature flag `NEXUS_STRICT_ENVELOPE=false` for one release cycle |
| PR-2 | ~180 | Low | Probe failures appear as new payment-log entries only |
| PR-3 | ~420 | Medium — `/api/query` response no longer has top-level `token` | Keep `token` field populated from the first identifier extracted, marked deprecated |
| PR-4 | ~350 | Low — endpoints keep same shape, source swap is internal | Legacy SQLite fields kept for one release under `legacy_cache_*` keys |
| PR-5 | ~200 | Low | `enrichments` defaults to `"auto"` (same observable behavior once agents declare suggestions) |
| PR-6 | ~300 | Medium UX — preset-button surface changes | Ship behind env flag `NEXT_PUBLIC_DYNAMIC_UI=true`; default on after one release |
| PR-7 | ~60 | Zero | Internal fix |
| PR-8 | depends on redeploy | High if contracts redeployed | Optional — skip unless perf warrants |

---

## 8. Definition of Done

A feature is done when the following all hold:

- [ ] `git grep -En "(PRESET_QUERIES|ENRICHMENT_CAPABILITIES|KNOWN_TOKENS|KNOWN_CRYPTO_CONTEXT|GoPlus-Security-Agent|Nexus-DataAgent|Nexus-AnalystAgent)" backend/ frontend/src/` returns **zero matches outside of tests and migration helpers**
- [ ] Any newly registered agent, with any capability name, is routed to for a matching query within 5 seconds of registration, with no backend code change
- [ ] `/api/reputation`, `/api/agents`, `/api/stats` serve correct data when `nexus.db` is moved aside (history arrays empty, everything else intact)
- [ ] Every invocation — success, failure, timeout, unreachable — produces: (a) an envelope in `report.sections`, (b) a WebSocket event with `status`, (c) a `payment_log` entry with matching status, (d) a reputation delta recorded on-chain
- [ ] Reports contain no field that no agent produced (`verdict: "N/A"` eradicated)
- [ ] Frontend suggestion pills, agent list, and register form are populated from `/api/capabilities` and `/api/agents` with zero hardcoded values
- [ ] Synthetic-agent test suite passes with 100% coverage of orchestration, discovery, envelope, probe, and chain-reader modules
- [ ] Running the three queries from 2026-04-17 (`AAVE TVL`, `UNI liquidity`, `USDC safety`) produces reports with `agents_involved ≥ 2`, envelopes for every selected capability, `output_fields` populated with whatever agents declared, and on-chain audit-trail tx hashes verifiable at testnet.kitescan.ai

---

## 9. Appendix — Dynamic Invariants, Stated Positively

These are the properties the finished system guarantees. They are the tests the DoD checks against.

1. **Unknown-is-OK:** The backend has no enum of valid capabilities, tokens, chains, or agents.
2. **Self-descriptive agents:** Each agent, at registration, fully describes what it consumes, produces, suggests, and costs.
3. **Schema-validated inputs:** Every agent receives input validated against its declared schema; malformed input never reaches the agent's business logic.
4. **Envelope-everything:** Success and failure are structurally identical. Downstream code branches on `status`, never on "which agent was this".
5. **Chain-first reads:** On-chain contracts are the source of truth for reputation, earnings, spending, payment counts. SQLite stores history, not totals.
6. **LLM-or-nothing routing:** No keyword fallback. When the router can't decide, the system tells the user, not a guess.
7. **Author-declared enrichments:** An agent opts in to being suggested alongside other capabilities by declaring the hint itself. The backend never decides this.
8. **Governance-backed constants:** Budget multipliers, TTLs, minimum reputation thresholds are read from `GovernanceRules`, not baked in.
9. **Frontend reflects backend:** All catalogs, suggestions, and fields the user sees are derived from live API reads, not build-time constants.
10. **Tests prove dynamism:** CI contains at least one synthetic-agent test for each of the above invariants.

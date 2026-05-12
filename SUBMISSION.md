# NEXUS — Kite AI Global Hackathon 2026 Submission

**Track:** Novel
**Live demo:** https://44-215-246-131.nip.io
**GitHub:** https://github.com/tarun-khatri/nexus-kiteAI-hackathon
**Block explorer (Kite Aero Testnet):** https://testnet.kitescan.ai

---

## What is NEXUS

NEXUS is a self-running economy of AI agents on Kite Chain. Multiple specialized agents discover each other through an open marketplace, sign cryptographic spending mandates, pay each other via x402 micropayments, build on-chain reputation, and produce verifiable audit trails — all without human-in-the-loop coordination.

It is **the first live system that uses all of Kite's four primitives — Agent Passport, x402 Payments, Verified Intent, and On-Chain Reputation — wired together into one continuously-running production economy.**

## The problem we solved

Billions of dollars have gone into AI agent startups (LangChain, Adept, Imbue, CrewAI, AutoGPT) — yet not a single agent in production today has paid another agent on-chain for a real service. AI agents are isolated tools: they have no shared identity, no shared payment rail, no shared rules, and no shared reputation. They can't form economies because the infrastructure to do so is missing.

Kite chain provides exactly those primitives. NEXUS proves they work together in production.

## What we built (live in production)

A complete autonomous-agent economy with eight functional components, all running 24/7 on AWS EC2 behind HTTPS:

1. **Four Solidity smart contracts** deployed on Kite Aero Testnet — `AgentRegistry` (identity), `PaymentRouter` (x402 settlement), `ReputationTracker` (on-chain reputation), `GovernanceRules` (spending limits).
2. **Eleven AI agents** currently registered — five built-in (DataAgent, AnalystAgent, ReportAgent, AuditAgent, plus orchestrator helpers) and three external HTTP agents (DeFiLlama-MetricsAgent, DEXScreener-Agent, GoPlus-Security-Agent) that self-registered through the open marketplace API. Anyone can add another with one API call.
3. **A pure-LLM dynamic router** — no hardcoded pipelines. The router reads a live capability registry built from agents' self-declared specs, asks an LLM which capabilities the query requires, and dispatches to whichever providers happen to be registered at that moment. New agents change what NEXUS can do automatically.
4. **ECDSA-signed Verified Intent mandates** with a seven-check programmable circuit breaker that gates every payment (budget, per-tx cap, daily cap, allowed-agents list, TTL, reputation floor, governance rules).
5. **Real on-chain x402 micropayments** between agents — every transaction is a verifiable Kitescan tx hash. As of submission: 1,293 transactions settled, $0.1487 USDC total volume.
6. **On-chain reputation system** — every agent has a reputation score updated after each job. The router prefers higher-reputation providers. Bad agents lose reputation and stop being selected; good ones compound.
7. **SHA-256 audit trail** for every query — traceability hash, report hash, mandate signature, and the on-chain transaction hash that recorded the audit on Kite, all queryable via `/api/audit-trail`.
8. **Market Pulse** — an autonomous trigger that fires every hour with no human in the loop. It pulls live market signals (BTC/ETH/SOL 24h delta, Fear and Greed Index, CoinGecko trending), uses an LLM to generate a genuinely emergent crypto-intelligence query each cycle (never from a hardcoded list), and runs the entire pipeline. **906 autonomous runs to date.** Public `/pulse` page lets anyone watch new runs land in real time with clickable Kitescan transaction hashes.

## Architecture & technology

- **Blockchain:** Kite Aero Testnet (Chain ID 2368). Four Solidity contracts, deployed and verified, called from Python via `web3.py`. x402 micropayments settled through the Pieverse facilitator.
- **Backend:** Python 3.11 + FastAPI + asyncio. SQLite in WAL mode with a single asyncio write-lock for guaranteed consistency under concurrent load. WebSocket for live event broadcasting.
- **AI Routing:** LLM router with automatic Groq → Gemini → Ollama fallback. Each provider has a 45-second hard timeout; failures gracefully degrade to the next provider. Free-tier only.
- **Frontend:** Next.js 16 (App Router) + TypeScript + Tailwind. Live counters, drill-down per-run views with full mandate signature and per-payment tx hashes. WebSocket subscription for real-time updates.
- **External agents:** registered via `POST /api/marketplace/register` with name, capabilities, callback URL, price. Capability registry rebuilds on registration. Agents can be written in any language (Python, Node, Go, Rust) — they just need to expose an HTTP endpoint matching the invocation envelope.
- **DevOps:** AWS EC2 t3.small + Docker Compose (7 services: caddy, backend, frontend, twitter-service, defi-agent, dexscreener-agent, security-agent). Caddy auto-provisions Let's Encrypt HTTPS via nip.io.
- **Tests:** 76 passing pytest tests covering capability registry, circuit breaker, identifier extraction, x402 protocol format, mandate signing, payment state machine, audit trail builder, and the autonomous pulse scheduler.

## Why this is novel

Four things in NEXUS exist in no other agent system today:

1. **Open marketplace** — every other agent framework (LangChain, CrewAI, AutoGPT, ChatGPT plugins) wires agents in code on one server. NEXUS exposes a public registration API; new agents from any provider join the live economy in seconds without us merging a single line of code.
2. **Dynamic LLM routing with zero hardcoded pipelines** — no `if query == "BTC" then call DataAgent` ladder. The router reads the live registry and routes purely on what's available right now.
3. **Autonomous trigger** — Market Pulse runs without human involvement. Every run is a real on-chain mandate + real x402 payments + real audit trail. 906 runs and counting.
4. **Full on-chain transparency** — every payment, every signature, every audit trail is a clickable Kitescan tx hash. Drill into any pulse run and see the ECDSA signature, signer address, per-payment from/to/amount, and the audit hash — no mocks, no proxies.

## What's next

- Mainnet on Kite when live — real USDC settlement
- Subscription mandates: recurring x402 payments on a signed schedule
- NEXUS Reputation Oracle: other dApps query agent reputation scores on-chain
- Agent SDK: one-line marketplace plug-in for any developer building on Kite
- DAO-governed spending rules: community-controlled governance contract parameters

The vision in one sentence: **Stripe gave the internet a payment rail. Yelp gave it reputation. Upwork gave it a marketplace. NEXUS gives the agent economy all three — on Kite.**

## Live production metrics at time of submission

| Metric | Value |
| --- | --- |
| Smart contracts deployed | 4 |
| AI agents in the economy | 11 |
| Distinct capabilities offered | 23 |
| On-chain transactions | 1,293 |
| Total USDC volume | $0.1487 |
| Jobs completed | 1,207 |
| Autonomous Market Pulse runs | 906 |
| Average reputation score | 64.1 / 100 |
| Backend tests | 76 passing |
| Operating cost | $0 / month (free tier only) |

## Verifying everything

1. **Browse the live site:** https://44-215-246-131.nip.io
2. **Watch autonomous runs land:** https://44-215-246-131.nip.io/pulse — bookmark this. Every hour a new row appears.
3. **Open the dashboard, click "Try live demo," type a crypto query** — watch the activity strip fire and click the audit-trail tx hash to see it on Kitescan.
4. **Click "Pulse" → expand any row** — see the ECDSA signature, signer address, individual x402 payment hashes, audit trail hash. Every single hash links to live Kitescan.
5. **Verify the four contracts on Kitescan:**
   - `AgentRegistry`: 0xBf23C1A79EfEf28C170cC8895679C4b4E7A97a74
   - `PaymentRouter`: 0xd76ea536704252DeD9602eCd549F776aD302c73C
   - `ReputationTracker`: 0xeE38c91e1dd42A0fc6980Ba8ECc769DFfC5044a9
   - `GovernanceRules`: 0xc7640Bf4fC973ac73bB381cb5a1f1f222db6671b
6. **Browse the open marketplace API** — `GET https://44-215-246-131.nip.io/api/agents` returns the live agent catalog.
7. **Run the test suite locally** — `git clone` the repo, `pytest backend/tests/` → 76 passed.

---
marp: true
theme: default
size: 16:9
paginate: true
backgroundColor: "#0E0E10"
color: "#F8F8F4"
style: |
  section {
    font-family: 'Inter', 'Space Grotesk', sans-serif;
    padding: 50px 70px;
    font-size: 22px;
  }
  h1 {
    font-size: 56px;
    font-weight: 800;
    letter-spacing: -0.02em;
    background: linear-gradient(120deg, #E86F2C 0%, #FCD34D 50%, #2563EB 100%);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
    margin-bottom: 0.2em;
  }
  h2 {
    font-size: 38px;
    font-weight: 700;
    color: #FCD34D;
    margin-bottom: 0.4em;
  }
  h3 {
    font-size: 22px;
    color: #E86F2C;
    margin-top: 0.6em;
    margin-bottom: 0.2em;
  }
  strong { color: #FCD34D; }
  em { color: #A0A0A0; font-style: normal; }
  code {
    background: #1A1A1F;
    color: #FCD34D;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 18px;
  }
  table {
    width: 100%;
    margin: 16px 0;
    border-collapse: collapse;
    font-size: 18px;
  }
  th {
    color: #FCD34D;
    text-align: left;
    border-bottom: 2px solid #E86F2C;
    padding: 8px 12px;
  }
  td {
    border-bottom: 1px solid #2A2A2F;
    padding: 8px 12px;
  }
  ul { line-height: 1.7; }
  li { margin-bottom: 6px; }
  section::after {
    content: attr(data-marpit-pagination) ' / ' attr(data-marpit-pagination-total);
    color: #555;
    font-size: 12px;
  }
  .footer {
    position: absolute;
    bottom: 28px;
    left: 70px;
    font-size: 14px;
    color: #555;
    letter-spacing: 0.05em;
  }
  .hero {
    text-align: center;
    padding-top: 80px;
  }
  .hero h1 { font-size: 92px; }
  .tagline {
    font-size: 26px;
    color: #FCD34D;
    margin-top: -10px;
  }
  .meta {
    font-size: 16px;
    color: #777;
    margin-top: 60px;
    line-height: 2;
  }
  .twocol {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 40px;
  }
  .stat-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 24px;
    margin-top: 30px;
  }
  .stat {
    background: #1A1A1F;
    border-left: 3px solid #E86F2C;
    padding: 18px 22px;
    border-radius: 6px;
  }
  .stat .num {
    font-size: 40px;
    font-weight: 800;
    color: #FCD34D;
    line-height: 1;
  }
  .stat .label {
    font-size: 13px;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-top: 6px;
  }
---

<!-- _class: hero -->

# NEXUS

<div class="tagline">The Living Agent Economy on Kite Chain</div>

<div class="meta">

**Kite AI Global Hackathon 2026 · Novel Track**

Live: **https://44-215-246-131.nip.io**
GitHub: **github.com/tarun-khatri/nexus-kiteAI-hackathon**
Chain: Kite Aero Testnet (2368)

</div>

<div class="footer">NEXUS · Slide 1 of 10</div>

---

## The problem

# Agents work alone today

Billions of dollars have gone into AI agents. **LangChain. AutoGPT. CrewAI. Adept. ChatGPT plugins.**

But not a single AI agent in production has ever paid another agent — **on-chain, for a real service.** They have:

- No shared **identity**
- No shared **payment rail**
- No shared **rules**
- No shared **reputation**

So they can't form economies. They sit as isolated tools, wired by hand into one company's server.

> *Working together requires manual coordination by humans. That breaks the moment an agent needs to hire another one outside its team.*

<div class="footer">2 / 10 · The problem</div>

---

## Why now

# Kite gives agents the missing primitives

The first chain purpose-built for autonomous AI agents:

| Primitive | What it gives an agent |
| --- | --- |
| **Agent Passport** | A real on-chain identity (queryable as a W3C-style DID) |
| **x402** | The native standard for paying machines per call |
| **Verified Intent** | Programmable spending rules a human signs |
| **On-chain Reputation** | A credit history bad actors can't fake |

NEXUS is the **first live system that uses all four — wired together as one running economy.**

<div class="footer">3 / 10 · Why now</div>

---

## The solution

# NEXUS — an open economy of AI agents

**Eleven AI agents. Twenty-three capabilities. One live marketplace on Kite.**

- Agents **discover each other** through a public capability registry
- **LLM router** dynamically picks the best agents per query — no hardcoded pipelines
- Every job runs under an **ECDSA-signed mandate** with a 7-check circuit breaker
- Agents **pay each other on-chain** via x402, settled on Kite testnet
- Every output is **audit-trailed on-chain** with a SHA-256 traceability hash
- An autonomous trigger — **Market Pulse** — runs the whole economy **without a human in the loop**

> *Anyone can register a new agent in a single API call. The marketplace grows itself.*

<div class="footer">4 / 10 · Solution</div>

---

## Live in production right now

# Real numbers, not slideware

<div class="stat-grid">
<div class="stat"><div class="num">1,293</div><div class="label">On-chain transactions</div></div>
<div class="stat"><div class="num">$0.1487</div><div class="label">USDC settled</div></div>
<div class="stat"><div class="num">906</div><div class="label">Autonomous runs</div></div>
<div class="stat"><div class="num">11</div><div class="label">Agents in the economy</div></div>
<div class="stat"><div class="num">23</div><div class="label">Capabilities offered</div></div>
<div class="stat"><div class="num">76</div><div class="label">Tests passing</div></div>
</div>

**Live URL → https://44-215-246-131.nip.io**
**Autonomous feed → https://44-215-246-131.nip.io/pulse**

> *Every transaction above corresponds to a verifiable Kitescan tx hash. Hover/click any payment in the dashboard to land directly on testnet.kitescan.ai.*

<div class="footer">5 / 10 · Traction</div>

---

## How it works

# One pipeline. Eight on-chain steps.

```
   User query  (or autonomous Market Pulse tick)
        │
        ▼
[1] LLM Router reads live capability registry  ──►  picks needed capabilities
        │
        ▼
[2] Capability Registry resolves capabilities  ──►  best provider per capability
        │                                              (sorted: reputation↑ price↓)
        ▼
[3] Mandate Manager signs spending mandate (ECDSA)
        │
        ▼
[4] Circuit Breaker — 7 checks per payment (budget · per-tx · daily · TTL · allowed-agents · reputation · governance)
        │
        ▼
[5] x402 Payment fires on Kite testnet (Pieverse facilitator)  ──►  tx hash returned
        │
        ▼
[6] Orchestrator invokes the agent over its callback URL (or in-process)
        │
        ▼
[7] AuditAgent verifies output  ──►  Reputation Tracker contract updated on-chain
        │
        ▼
[8] Audit Trail Builder records SHA-256 traceability hash on-chain
```

<div class="footer">6 / 10 · Architecture</div>

---

## Agent autonomy

# Market Pulse runs while we're talking

Every hour, the backend wakes itself up — no human involvement.

**1.** Pulls **live market signals** (BTC/ETH/SOL 24h delta, Fear & Greed, CoinGecko trending)
**2.** Asks an LLM to **generate a fresh query** based on current conditions (never from a list)
**3.** Drives the **full pipeline** — mandate, x402 payments, audit trail, reputation update
**4.** Persists the run to `/pulse` — drillable to the ECDSA signature, per-payment from→to, and Kitescan tx hash

**906 autonomous runs to date.** Bookmark `/pulse` and watch run #907 land on its own.

> *This is not a scheduled cron job calling a static endpoint. It is an end-to-end agent economy running itself, with every transaction settled on-chain.*

<div class="footer">7 / 10 · Autonomy</div>

---

## Developer experience

# A new agent joins in one API call

```http
POST /api/marketplace/register
{
  "name": "MyCustom-Agent-v1",
  "description": "Tracks Solana memecoins...",
  "capabilities": ["memecoin_discovery"],
  "callback_url": "https://my-agent.example.com/invoke",
  "price_per_query": 0.0001,
  "keywords": ["memecoin", "solana", "trending"],
  "example_queries": ["new Solana memes today"]
}
```

That agent is **live in the economy** the moment the call returns. The capability registry rebuilds. The LLM router picks it up. It starts earning x402 payments. Reputation begins compounding.

- **Any language.** Python, Node, Go, Rust — only needs an HTTP endpoint matching the invocation envelope.
- **No code review.** No team merge. No proxy permission.
- **Real settlement** from minute zero — every successful job is a real Kite testnet tx.

<div class="footer">8 / 10 · DevEx</div>

---

## What makes NEXUS different

# Four things no other agent framework has

| | LangChain / CrewAI | ChatGPT Plugins | Coinbase AgentKit | **NEXUS** |
| --- | :---: | :---: | :---: | :---: |
| **Open marketplace** | ✗ | ✗ | ✗ | **✓** |
| **Native machine payments (x402)** | ✗ | ✗ | partial | **✓ on-chain** |
| **Verified Intent (ECDSA mandates)** | ✗ | ✗ | ✗ | **✓ 7-check** |
| **On-chain reputation** | ✗ | ✗ | ✗ | **✓** |
| **Autonomous trigger, no human** | ✗ | ✗ | ✗ | **✓** |
| **Pure-LLM dynamic routing** | partial | ✗ | ✗ | **✓** |

**Built on free-tier infrastructure.** Groq + Gemini fallback + Kite testnet + AWS t3.small.
**Total cost to operate this in production: $0 / month.**

<div class="footer">9 / 10 · Differentiation</div>

---

<!-- _class: hero -->

# What comes next.

<div style="text-align:left; font-size: 22px; line-height: 1.9; margin-top: 30px;">

**Now** — Live on Kite Aero Testnet · open source · 906 autonomous runs

**+30 days** — Subscription mandates · recurring x402 on signed schedules

**+60 days** — NEXUS Reputation Oracle · any dApp on Kite queries agent rep on-chain

**+90 days** — Agent SDK · one-line marketplace plug-in for any builder on Kite

**Mainnet** — Real USDC settlement when Kite mainnet ships

</div>

<div class="tagline" style="margin-top: 40px; font-size: 22px;">

*Stripe gave the internet a payment rail. Yelp gave it reputation.*
*Upwork gave it a marketplace. **NEXUS gives the agent economy all three — on Kite.***

</div>

<div class="meta" style="margin-top: 50px; font-size: 18px;">

**Live:** https://44-215-246-131.nip.io
**GitHub:** github.com/tarun-khatri/nexus-kiteAI-hackathon
**Built by:** Tarun Khatri

</div>

<div class="footer">10 / 10 · Vision</div>

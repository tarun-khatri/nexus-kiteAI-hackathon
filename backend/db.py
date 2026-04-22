"""
NEXUS - SQLite Persistence Layer

Stores transaction history, audit trails, reputation events, mandates,
AND registered marketplace agents so that ALL state survives server restarts.

On startup, main.py calls the load_*() functions to rehydrate:
  - Agent transactions + totals (total_earned, total_spent, jobs)
  - Reputation history (for transparent scoring timeline)
  - Completed mandates (full query history)
  - Audit trails (on-chain traceability records)
  - Marketplace agents (external agents that registered previously)

On-chain data (reputation scores in ReputationTracker, registrations in
AgentRegistry) is ALSO read separately at startup -- the DB caches the
faster/richer data, the chain is the authoritative reputation source.
"""

import os
import aiosqlite
import json
from datetime import datetime
from pathlib import Path

# DB location. Default sits next to this file (dev mode). In production,
# set NEXUS_DB_PATH to a path inside a persistent Docker volume so data
# survives `docker compose down` and image rebuilds.
DB_PATH = os.getenv(
    "NEXUS_DB_PATH",
    str(Path(__file__).parent / "nexus.db"),
)

# Make sure the parent directory exists (in case NEXUS_DB_PATH points at
# a newly-mounted empty volume).
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)


# ============================================================
# Schema initialization
# ============================================================

async def init_db():
    """Initialize all tables if they don't exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS transactions (
            id TEXT PRIMARY KEY,
            from_agent TEXT NOT NULL,
            to_agent TEXT NOT NULL,
            amount REAL NOT NULL,
            purpose TEXT,
            tx_hash TEXT,
            status TEXT,
            mandate_id TEXT,
            timestamp TEXT NOT NULL
        )""")
        await db.execute("""CREATE INDEX IF NOT EXISTS idx_tx_from ON transactions(from_agent)""")
        await db.execute("""CREATE INDEX IF NOT EXISTS idx_tx_to ON transactions(to_agent)""")

        await db.execute("""CREATE TABLE IF NOT EXISTS audit_trails (
            trail_id TEXT PRIMARY KEY,
            mandate_id TEXT,
            traceability_hash TEXT NOT NULL,
            report_hash TEXT,
            on_chain_tx_hash TEXT,
            explorer_url TEXT,
            query TEXT,
            timestamp TEXT NOT NULL
        )""")

        await db.execute("""CREATE TABLE IF NOT EXISTS reputation_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            old_score INTEGER,
            new_score INTEGER,
            change INTEGER,
            reason TEXT,
            timestamp TEXT NOT NULL
        )""")
        await db.execute("""CREATE INDEX IF NOT EXISTS idx_rep_agent ON reputation_events(agent_name)""")

        await db.execute("""CREATE TABLE IF NOT EXISTS mandates (
            mandate_id TEXT PRIMARY KEY,
            query TEXT,
            context_hash TEXT,
            total_budget REAL,
            total_spent REAL,
            status TEXT,
            signature TEXT,
            signer_address TEXT,
            timestamp TEXT NOT NULL
        )""")

        # NEW: persistent marketplace registrations (external agents)
        await db.execute("""CREATE TABLE IF NOT EXISTS marketplace_agents (
            agent_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            capabilities_json TEXT,
            keywords_json TEXT,
            example_queries_json TEXT,
            price_per_query REAL,
            callback_url TEXT,
            owner_address TEXT,
            passport_id TEXT,
            reputation_score INTEGER,
            total_jobs INTEGER,
            active INTEGER,
            registered_at TEXT,
            last_invoked TEXT
        )""")

        # WebSocket event history (survives backend + frontend restarts)
        await db.execute("""CREATE TABLE IF NOT EXISTS ws_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_json TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )""")

        await db.commit()
    print("[DB] SQLite persistence initialized")


# ============================================================
# Save functions (called during normal operation)
# ============================================================

async def save_transaction(tx: dict):
    """Persist a transaction record."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO transactions VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    tx.get("tx_id", ""),
                    tx.get("from_agent", ""),
                    tx.get("to_agent", ""),
                    tx.get("amount", 0),
                    tx.get("purpose", ""),
                    tx.get("tx_hash", ""),
                    tx.get("status", ""),
                    tx.get("mandate_id", ""),
                    datetime.utcnow().isoformat(),
                ),
            )
            await db.commit()
    except Exception as e:
        print(f"[DB] Error saving transaction: {e}")


async def save_audit_trail(trail: dict):
    """Persist an audit trail entry."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO audit_trails VALUES (?,?,?,?,?,?,?,?)",
                (
                    trail.get("trail_id", ""),
                    trail.get("mandate_id", ""),
                    trail.get("traceability_hash", ""),
                    trail.get("report_hash", ""),
                    trail.get("on_chain_tx_hash", ""),
                    trail.get("explorer_url", ""),
                    trail.get("query", ""),
                    datetime.utcnow().isoformat(),
                ),
            )
            await db.commit()
    except Exception as e:
        print(f"[DB] Error saving audit trail: {e}")


async def save_reputation_event(agent_name: str, old_score: int, new_score: int, change: int, reason: str):
    """Persist a reputation change event."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO reputation_events (agent_name, old_score, new_score, change, reason, timestamp) VALUES (?,?,?,?,?,?)",
                (agent_name, old_score, new_score, change, reason, datetime.utcnow().isoformat()),
            )
            await db.commit()
    except Exception as e:
        print(f"[DB] Error saving reputation event: {e}")


async def save_mandate(mandate: dict):
    """Persist a mandate record."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO mandates VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    mandate.get("mandate_id", ""),
                    mandate.get("query", ""),
                    mandate.get("context_hash", ""),
                    mandate.get("total_budget", 0),
                    mandate.get("total_spent", 0),
                    mandate.get("status", ""),
                    mandate.get("signature", ""),
                    mandate.get("signer_address", ""),
                    datetime.utcnow().isoformat(),
                ),
            )
            await db.commit()
    except Exception as e:
        print(f"[DB] Error saving mandate: {e}")


async def save_marketplace_agent(agent: dict):
    """Persist a marketplace agent registration."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO marketplace_agents VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    agent.get("agent_id", ""),
                    agent.get("name", ""),
                    agent.get("description", ""),
                    json.dumps(agent.get("capabilities") or []),
                    json.dumps(agent.get("keywords") or []),
                    json.dumps(agent.get("example_queries") or []),
                    agent.get("price_per_query", 0),
                    agent.get("callback_url", ""),
                    agent.get("owner_address", ""),
                    agent.get("passport_id", "") or "",
                    int(agent.get("reputation_score", 50)),
                    int(agent.get("total_jobs", 0)),
                    1 if agent.get("active", True) else 0,
                    agent.get("registered_at") or datetime.utcnow().isoformat(),
                    agent.get("last_invoked") or "",
                ),
            )
            await db.commit()
    except Exception as e:
        print(f"[DB] Error saving marketplace agent: {e}")


# ============================================================
# Load functions (called on startup to rehydrate state)
# ============================================================

async def load_agent_totals(agent_name: str) -> dict:
    """
    Compute earnings/spending/jobs from saved transactions.
    Returns: {"total_earned": float, "total_spent": float, "total_jobs": int}
    """
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE to_agent = ? AND status != 'failed'",
                (agent_name,),
            )
            earned = (await cur.fetchone())[0] or 0.0

            cur = await db.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE from_agent = ? AND status != 'failed'",
                (agent_name,),
            )
            spent = (await cur.fetchone())[0] or 0.0

            # Jobs completed = unique mandates this agent participated in (as payee)
            cur = await db.execute(
                "SELECT COUNT(DISTINCT mandate_id) FROM transactions WHERE to_agent = ? AND status != 'failed' AND mandate_id != ''",
                (agent_name,),
            )
            jobs = (await cur.fetchone())[0] or 0

            return {
                "total_earned": float(earned),
                "total_spent": float(spent),
                "total_jobs": int(jobs),
            }
    except Exception as e:
        print(f"[DB] Error loading totals for {agent_name}: {e}")
        return {"total_earned": 0.0, "total_spent": 0.0, "total_jobs": 0}


async def load_agent_transactions(agent_name: str, limit: int = 100) -> list[dict]:
    """
    Return recent transactions involving this agent (as payer OR payee).
    Most recent first.
    """
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                """SELECT id, from_agent, to_agent, amount, purpose, tx_hash, status, mandate_id, timestamp
                   FROM transactions
                   WHERE from_agent = ? OR to_agent = ?
                   ORDER BY timestamp DESC
                   LIMIT ?""",
                (agent_name, agent_name, limit),
            )
            rows = await cur.fetchall()
            return [
                {
                    "tx_id": r[0],
                    "from_agent": r[1],
                    "to_agent": r[2],
                    "amount": r[3],
                    "purpose": r[4] or "",
                    "tx_hash": r[5] or "",
                    "status": r[6] or "",
                    "mandate_id": r[7] or "",
                    "timestamp": r[8],
                }
                for r in rows
            ]
    except Exception as e:
        print(f"[DB] Error loading transactions for {agent_name}: {e}")
        return []


async def load_reputation_history(agent_name: str, limit: int = 100) -> list[dict]:
    """Return recent reputation change events for this agent."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                """SELECT old_score, new_score, change, reason, timestamp
                   FROM reputation_events
                   WHERE agent_name = ?
                   ORDER BY timestamp DESC
                   LIMIT ?""",
                (agent_name, limit),
            )
            rows = await cur.fetchall()
            # Return in chronological order (oldest first) for a stable timeline.
            rows_asc = list(reversed(rows))
            return [
                {
                    "timestamp": r[4],
                    "old_score": r[0],
                    "new_score": r[1],
                    "change": r[2],
                    "reason": r[3] or "",
                    "direction": "up" if r[2] > 0 else "down" if r[2] < 0 else "unchanged",
                }
                for r in rows_asc
            ]
    except Exception as e:
        print(f"[DB] Error loading reputation history for {agent_name}: {e}")
        return []


async def load_audit_trails(limit: int = 100) -> list[dict]:
    """Return recent audit trail entries, newest first."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                """SELECT trail_id, mandate_id, traceability_hash, report_hash,
                          on_chain_tx_hash, explorer_url, query, timestamp
                   FROM audit_trails ORDER BY timestamp DESC LIMIT ?""",
                (limit,),
            )
            rows = await cur.fetchall()
            return [
                {
                    "trail_id": r[0],
                    "mandate_id": r[1] or "",
                    "traceability_hash": r[2],
                    "report_hash": r[3] or "",
                    "on_chain_tx_hash": r[4] or "",
                    "explorer_url": r[5] or "",
                    "query": r[6] or "",
                    "timestamp": r[7],
                }
                for r in rows
            ]
    except Exception as e:
        print(f"[DB] Error loading audit trails: {e}")
        return []


async def load_completed_mandates(limit: int = 100) -> list[dict]:
    """Return recent completed mandates, newest first."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                """SELECT mandate_id, query, context_hash, total_budget, total_spent,
                          status, signature, signer_address, timestamp
                   FROM mandates ORDER BY timestamp DESC LIMIT ?""",
                (limit,),
            )
            rows = await cur.fetchall()
            return [
                {
                    "mandate_id": r[0],
                    "query": r[1] or "",
                    "context_hash": r[2] or "",
                    "total_budget": r[3] or 0,
                    "total_spent": r[4] or 0,
                    "status": r[5] or "",
                    "signature": r[6] or "",
                    "signer_address": r[7] or "",
                    "timestamp": r[8],
                }
                for r in rows
            ]
    except Exception as e:
        print(f"[DB] Error loading mandates: {e}")
        return []


async def load_marketplace_agents() -> list[dict]:
    """Return all persisted marketplace agent registrations."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                """SELECT agent_id, name, description, capabilities_json, keywords_json,
                          example_queries_json, price_per_query, callback_url,
                          owner_address, passport_id, reputation_score, total_jobs,
                          active, registered_at, last_invoked
                   FROM marketplace_agents"""
            )
            rows = await cur.fetchall()
            out = []
            for r in rows:
                try:
                    caps = json.loads(r[3] or "[]")
                    keywords = json.loads(r[4] or "[]")
                    examples = json.loads(r[5] or "[]")
                except Exception:
                    caps, keywords, examples = [], [], []
                out.append({
                    "agent_id": r[0],
                    "name": r[1],
                    "description": r[2] or "",
                    "capabilities": caps,
                    "keywords": keywords,
                    "example_queries": examples,
                    "price_per_query": r[6] or 0,
                    "callback_url": r[7] or "",
                    "owner_address": r[8] or "",
                    "passport_id": r[9] or None,
                    "reputation_score": r[10] or 50,
                    "total_jobs": r[11] or 0,
                    "active": bool(r[12]),
                    "registered_at": r[13],
                    "last_invoked": r[14] or None,
                })
            return out
    except Exception as e:
        print(f"[DB] Error loading marketplace agents: {e}")
        return []


# ============================================================
# Misc helpers
# ============================================================

async def get_transaction_count() -> int:
    """Get total stored transaction count."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM transactions")
            row = await cursor.fetchone()
            return row[0] if row else 0
    except Exception:
        return 0


async def get_audit_trail_count() -> int:
    """Get total stored audit trail count."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM audit_trails")
            row = await cursor.fetchone()
            return row[0] if row else 0
    except Exception:
        return 0


# ============================================================
# WebSocket Event History (persists across restarts)
# ============================================================

async def save_ws_event(event_json: str):
    """Persist a WebSocket event so the transaction feed survives restarts."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO ws_events (event_json, timestamp) VALUES (?, ?)",
                (event_json, datetime.utcnow().isoformat()),
            )
            # Keep only the last 500 events to prevent table bloat.
            await db.execute(
                "DELETE FROM ws_events WHERE id NOT IN (SELECT id FROM ws_events ORDER BY id DESC LIMIT 500)"
            )
            await db.commit()
    except Exception:
        pass  # best-effort


async def load_ws_events(limit: int = 200) -> list[dict]:
    """Load persisted WebSocket events (newest first) for transaction feed recovery."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "SELECT event_json FROM ws_events ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            rows = await cur.fetchall()
            events = []
            for r in rows:
                try:
                    events.append(json.loads(r[0]))
                except Exception:
                    pass
            return events  # newest first
    except Exception:
        return []

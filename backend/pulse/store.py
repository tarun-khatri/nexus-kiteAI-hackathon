"""
Pulse runs persistence — CRUD over the `pulse_runs` SQLite table.

Follows the same write-lock + WAL-pragma pattern as every other save_* in
backend/db.py: writes go through `_db_write_lock` + `_open_writable()`, reads
open a plain connection (WAL lets readers run in parallel with the single
writer).
"""

from __future__ import annotations

import json
from typing import Optional

import aiosqlite

from backend.db import DB_PATH, _db_write_lock, _open_writable


# ============================================================
# Write path (through the shared write lock)
# ============================================================

async def save_pulse_run(run: dict) -> None:
    """
    Persist a single pulse run. Idempotent on run_id — repeated calls replace
    the row (used so a retry-after-partial-failure path could overwrite cleanly;
    in practice each run gets a fresh uuid).
    """
    try:
        async with _db_write_lock:
            db = await _open_writable()
            try:
                await db.execute(
                    """INSERT OR REPLACE INTO pulse_runs (
                        run_id, query, trigger_source, report_id, summary, status,
                        agents_involved, total_cost_usdc, total_time_ms,
                        audit_tx_hash, payment_tx_hashes_json, mandate_id,
                        error_message, started_at, completed_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        run.get("run_id", ""),
                        run.get("query", ""),
                        run.get("trigger_source", "scheduled"),
                        run.get("report_id"),
                        run.get("summary"),
                        run.get("status", "ok"),
                        int(run.get("agents_involved") or 0),
                        float(run.get("total_cost_usdc") or 0.0),
                        int(run.get("total_time_ms") or 0),
                        run.get("audit_tx_hash"),
                        run.get("payment_tx_hashes_json") or json.dumps([]),
                        run.get("mandate_id"),
                        run.get("error_message"),
                        run.get("started_at", ""),
                        run.get("completed_at"),
                    ),
                )
                await db.commit()
            finally:
                await db.close()
    except Exception as e:
        print(f"[DB] Error saving pulse run: {e}")


# ============================================================
# Read path (plain connections — WAL allows concurrent reads)
# ============================================================

def _row_to_dict(row) -> dict:
    """Convert a sqlite Row tuple to the API-shaped dict."""
    tx_list: list = []
    if row[10]:
        try:
            tx_list = json.loads(row[10])
            if not isinstance(tx_list, list):
                tx_list = []
        except Exception:
            tx_list = []
    return {
        "run_id": row[0],
        "query": row[1],
        "trigger_source": row[2],
        "report_id": row[3],
        "summary": row[4],
        "status": row[5],
        "agents_involved": row[6] or 0,
        "total_cost_usdc": row[7] or 0.0,
        "total_time_ms": row[8] or 0,
        "audit_tx_hash": row[9],
        "payment_tx_hashes": tx_list,
        "mandate_id": row[11],
        "error_message": row[12],
        "started_at": row[13],
        "completed_at": row[14],
    }


async def load_pulse_runs(limit: int = 50) -> list[dict]:
    """Newest-first. Caps at 500 rows to prevent pathological requests."""
    limit = max(1, min(int(limit), 500))
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                """SELECT run_id, query, trigger_source, report_id, summary, status,
                          agents_involved, total_cost_usdc, total_time_ms,
                          audit_tx_hash, payment_tx_hashes_json, mandate_id,
                          error_message, started_at, completed_at
                   FROM pulse_runs
                   ORDER BY started_at DESC
                   LIMIT ?""",
                (limit,),
            )
            rows = await cur.fetchall()
            return [_row_to_dict(r) for r in rows]
    except Exception as e:
        print(f"[DB] Error loading pulse runs: {e}")
        return []


async def load_pulse_run(run_id: str) -> Optional[dict]:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                """SELECT run_id, query, trigger_source, report_id, summary, status,
                          agents_involved, total_cost_usdc, total_time_ms,
                          audit_tx_hash, payment_tx_hashes_json, mandate_id,
                          error_message, started_at, completed_at
                   FROM pulse_runs
                   WHERE run_id = ?""",
                (run_id,),
            )
            row = await cur.fetchone()
            return _row_to_dict(row) if row else None
    except Exception as e:
        print(f"[DB] Error loading pulse run {run_id}: {e}")
        return None


async def count_pulse_runs(since_iso: Optional[str] = None) -> int:
    """Total runs. Optionally filter to runs started after `since_iso` (UTC)."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            if since_iso:
                cur = await db.execute(
                    "SELECT COUNT(*) FROM pulse_runs WHERE started_at >= ?",
                    (since_iso,),
                )
            else:
                cur = await db.execute("SELECT COUNT(*) FROM pulse_runs")
            row = await cur.fetchone()
            return int(row[0] if row else 0)
    except Exception as e:
        print(f"[DB] Error counting pulse runs: {e}")
        return 0

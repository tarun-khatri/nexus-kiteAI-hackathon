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
                        run_id, query, trigger_source, query_source,
                        report_id, summary, status,
                        agents_involved, total_cost_usdc, total_time_ms,
                        audit_tx_hash, payment_tx_hashes_json, mandate_id,
                        error_message, started_at, completed_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        run.get("run_id", ""),
                        run.get("query", ""),
                        run.get("trigger_source", "scheduled"),
                        run.get("query_source"),
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
    """
    Convert a sqlite Row tuple to the API-shaped dict.

    v2 stores payments as a rich list of dicts:
      [{"from_agent":..., "to_agent":..., "amount":..., "purpose":...,
        "tx_hash":..., "status":...}, ...]

    v1 rows (the 2 already in prod) stored a flat list[str] of tx hashes.
    We transparently wrap v1 entries as minimal dicts so the frontend can
    treat both uniformly — old rows just show blank from/to/purpose.

    Column order (must match the SELECT below):
      0  run_id
      1  query
      2  trigger_source
      3  query_source
      4  report_id
      5  summary
      6  status
      7  agents_involved
      8  total_cost_usdc
      9  total_time_ms
      10 audit_tx_hash
      11 payment_tx_hashes_json
      12 mandate_id
      13 error_message
      14 started_at
      15 completed_at
    """
    raw_payments = row[11]
    parsed: list = []
    if raw_payments:
        try:
            parsed = json.loads(raw_payments)
            if not isinstance(parsed, list):
                parsed = []
        except Exception:
            parsed = []

    payments: list[dict] = []
    for item in parsed:
        if isinstance(item, dict):
            # v2 rich format — normalize keys we expect.
            payments.append({
                "from_agent": item.get("from_agent") or item.get("from") or "",
                "to_agent": item.get("to_agent") or item.get("to") or "",
                "amount": float(item.get("amount") or 0.0),
                "purpose": item.get("purpose") or "",
                "tx_hash": item.get("tx_hash") or "",
                "status": item.get("status") or "confirmed",
            })
        elif isinstance(item, str):
            # v1 legacy format — bare tx hash string. Wrap it.
            payments.append({
                "from_agent": "",
                "to_agent": "",
                "amount": 0.0,
                "purpose": "",
                "tx_hash": item,
                "status": "confirmed",
            })
        # anything else is ignored silently

    return {
        "run_id": row[0],
        "query": row[1],
        "trigger_source": row[2],
        "query_source": row[3],
        "report_id": row[4],
        "summary": row[5],
        "status": row[6],
        "agents_involved": row[7] or 0,
        "total_cost_usdc": row[8] or 0.0,
        "total_time_ms": row[9] or 0,
        "audit_tx_hash": row[10],
        "payments": payments,
        "mandate_id": row[12],
        "error_message": row[13],
        "started_at": row[14],
        "completed_at": row[15],
    }


async def load_pulse_runs(limit: int = 50) -> list[dict]:
    """Newest-first. Caps at 500 rows to prevent pathological requests."""
    limit = max(1, min(int(limit), 500))
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                """SELECT run_id, query, trigger_source, query_source,
                          report_id, summary, status,
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
                """SELECT run_id, query, trigger_source, query_source,
                          report_id, summary, status,
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

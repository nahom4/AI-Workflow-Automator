"""
libsql-client wrapper that mirrors the Next.js db schema.
Connects to Turso in production, local SQLite file in development.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import libsql_client

from worker.config import TURSO_URL, TURSO_TOKEN, DATABASE_PATH


def _make_client() -> libsql_client.Client:
    if TURSO_URL and TURSO_TOKEN:
        return libsql_client.create_client(url=TURSO_URL, auth_token=TURSO_TOKEN)
    db_path = Path(DATABASE_PATH).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return libsql_client.create_client(url=f"file:{db_path}")


_client: libsql_client.Client | None = None


def get_client() -> libsql_client.Client:
    global _client
    if _client is None:
        _client = _make_client()
    return _client


async def fetch_due_automations() -> list[dict]:
    """Return all active automations whose next_run_at is <= now."""
    now = int(time.time() * 1000)
    rs = await get_client().execute(
        libsql_client.Statement(
            "SELECT * FROM automations WHERE status = 'active' AND next_run_at <= ?",
            [now],
        )
    )
    return [dict(zip(rs.columns, row)) for row in rs.rows]


async def insert_run(run_id: str, automation_id: str) -> None:
    now = int(time.time() * 1000)
    await get_client().execute(
        libsql_client.Statement(
            "INSERT INTO runs (id, automation_id, status, started_at) VALUES (?, ?, 'running', ?)",
            [run_id, automation_id, now],
        )
    )


async def finish_run(
    run_id: str,
    *,
    status: str,
    items_seen: int = 0,
    items_kept: int = 0,
    errors: list | None = None,
) -> None:
    now = int(time.time() * 1000)
    await get_client().execute(
        libsql_client.Statement(
            """UPDATE runs
               SET status = ?, finished_at = ?, items_seen = ?, items_kept = ?, errors_json = ?
               WHERE id = ?""",
            [
                status,
                now,
                items_seen,
                items_kept,
                json.dumps(errors) if errors else None,
                run_id,
            ],
        )
    )


async def append_run_log(run_id: str, level: str, message: str) -> None:
    import nanoid  # type: ignore

    now = int(time.time() * 1000)
    log_id = nanoid.generate(size=10)
    await get_client().execute(
        libsql_client.Statement(
            "INSERT INTO run_logs (id, run_id, level, message, created_at) VALUES (?, ?, ?, ?, ?)",
            [log_id, run_id, level, message, now],
        )
    )


async def update_automation_schedule(
    automation_id: str, *, last_run_at: int, next_run_at: int
) -> None:
    now = int(time.time() * 1000)
    await get_client().execute(
        libsql_client.Statement(
            "UPDATE automations SET last_run_at = ?, next_run_at = ?, updated_at = ? WHERE id = ?",
            [last_run_at, next_run_at, now, automation_id],
        )
    )


async def mark_automation_broken(automation_id: str) -> None:
    now = int(time.time() * 1000)
    await get_client().execute(
        libsql_client.Statement(
            "UPDATE automations SET status = 'broken', updated_at = ? WHERE id = ?",
            [now, automation_id],
        )
    )


async def upsert_lead(
    *,
    lead_id: str,
    automation_id: str,
    source_domain: str,
    external_id: str,
    url: str,
    title: str,
    raw_json: dict,
    score: float,
    matched_reasons: str | None = None,
) -> bool:
    """Insert lead; returns True if it was new (not a duplicate)."""
    now = int(time.time() * 1000)
    rs = await get_client().execute(
        libsql_client.Statement(
            """INSERT OR IGNORE INTO leads
               (id, automation_id, source_domain, external_id, url, title, raw_json, score, matched_reasons, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                lead_id,
                automation_id,
                source_domain,
                external_id,
                url,
                title,
                json.dumps(raw_json),
                score,
                matched_reasons,
                now,
            ],
        )
    )
    return rs.rows_affected > 0


async def get_site_spec(domain: str, vertical: str) -> dict | None:
    rs = await get_client().execute(
        libsql_client.Statement(
            "SELECT * FROM site_specs WHERE domain = ? AND vertical = ?",
            [domain, vertical],
        )
    )
    if not rs.rows:
        return None
    return dict(zip(rs.columns, rs.rows[0]))


async def upsert_site_spec(
    domain: str,
    vertical: str,
    tier: str,
    spec: dict,
    *,
    user_confirmed: bool = False,
) -> None:
    now = int(time.time() * 1000)
    await get_client().execute(
        libsql_client.Statement(
            """INSERT INTO site_specs (domain, vertical, tier, spec_json, user_confirmed, last_validated_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(domain, vertical) DO UPDATE SET
                 tier = excluded.tier,
                 spec_json = excluded.spec_json,
                 user_confirmed = excluded.user_confirmed,
                 last_validated_at = excluded.last_validated_at""",
            [domain, vertical, tier, json.dumps(spec), int(user_confirmed), now, now],
        )
    )

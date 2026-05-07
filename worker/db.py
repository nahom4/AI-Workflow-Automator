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

try:
    import libsql_client
except ImportError:
    # libsql-client not available locally — use the bundled sqlite3 stub
    import sys, types as _types, pathlib as _pathlib
    _stub_path = str(_pathlib.Path(__file__).parent.parent / "tests" / "python")
    if _stub_path not in sys.path:
        sys.path.insert(0, _stub_path)
    from _libsql_stub import Statement as _S, create_client as _cc  # type: ignore
    libsql_client = _types.ModuleType("libsql_client")  # type: ignore
    libsql_client.Statement = _S  # type: ignore
    libsql_client.create_client = _cc  # type: ignore

from worker.config import TURSO_URL, TURSO_TOKEN, DATABASE_PATH


def _make_client():  # type: ignore[return]
    if TURSO_URL and TURSO_TOKEN:
        return libsql_client.create_client(url=TURSO_URL, auth_token=TURSO_TOKEN)
    db_path = Path(DATABASE_PATH).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return libsql_client.create_client(url=f"file:{db_path}")


_client = None


def get_client():
    global _client
    if _client is None:
        _client = _make_client()
    return _client


_SCHEMA_STMTS = [
    """CREATE TABLE IF NOT EXISTS automations (
      id TEXT PRIMARY KEY, name TEXT NOT NULL, intent_text TEXT NOT NULL,
      vertical TEXT NOT NULL DEFAULT 'other', spec_json TEXT NOT NULL,
      schedule_cron TEXT NOT NULL, notify_email TEXT, notify_whatsapp TEXT,
      status TEXT NOT NULL DEFAULT 'active', last_run_at INTEGER,
      next_run_at INTEGER NOT NULL, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS leads (
      id TEXT PRIMARY KEY, automation_id TEXT NOT NULL REFERENCES automations(id) ON DELETE CASCADE,
      source_domain TEXT NOT NULL, external_id TEXT NOT NULL, url TEXT NOT NULL,
      title TEXT NOT NULL, raw_json TEXT NOT NULL, score REAL NOT NULL,
      matched_reasons TEXT, notified_at INTEGER, created_at INTEGER NOT NULL,
      UNIQUE(automation_id, external_id)
    )""",
    """CREATE TABLE IF NOT EXISTS site_specs (
      domain TEXT NOT NULL, vertical TEXT NOT NULL, tier TEXT NOT NULL,
      spec_json TEXT NOT NULL, user_confirmed INTEGER NOT NULL DEFAULT 0,
      last_validated_at INTEGER, success_rate REAL, created_at INTEGER NOT NULL,
      PRIMARY KEY (domain, vertical)
    )""",
    """CREATE TABLE IF NOT EXISTS runs (
      id TEXT PRIMARY KEY, automation_id TEXT NOT NULL REFERENCES automations(id) ON DELETE CASCADE,
      status TEXT NOT NULL DEFAULT 'running', started_at INTEGER NOT NULL,
      finished_at INTEGER, items_seen INTEGER DEFAULT 0, items_kept INTEGER DEFAULT 0, errors_json TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS run_logs (
      id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
      level TEXT NOT NULL, message TEXT NOT NULL, created_at INTEGER NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_automations_next_run ON automations(next_run_at, status)",
    "CREATE INDEX IF NOT EXISTS idx_leads_automation_id ON leads(automation_id)",
    "CREATE INDEX IF NOT EXISTS idx_runs_automation_id ON runs(automation_id)",
    "CREATE INDEX IF NOT EXISTS idx_run_logs_run_id ON run_logs(run_id)",
]


async def ensure_schema() -> None:
    """Create all tables if they don't exist. Safe to call on every startup."""
    client = get_client()
    for stmt in _SCHEMA_STMTS:
        await client.execute(libsql_client.Statement(stmt))


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

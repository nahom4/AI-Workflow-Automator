"""
Integration tests for worker.db — runs against a real in-process SQLite
via the libsql_client stub injected in conftest.py.
"""

from __future__ import annotations

import json
import time

import pytest

import worker.db as db_module
from tests.python._libsql_stub import create_client

_SCHEMA = """
CREATE TABLE IF NOT EXISTS automations (
  id              TEXT PRIMARY KEY,
  name            TEXT NOT NULL,
  intent_text     TEXT NOT NULL,
  vertical        TEXT NOT NULL DEFAULT 'other',
  spec_json       TEXT NOT NULL,
  schedule_cron   TEXT NOT NULL,
  notify_email    TEXT,
  notify_whatsapp TEXT,
  status          TEXT NOT NULL DEFAULT 'active',
  last_run_at     INTEGER,
  next_run_at     INTEGER NOT NULL,
  created_at      INTEGER NOT NULL,
  updated_at      INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS leads (
  id              TEXT PRIMARY KEY,
  automation_id   TEXT NOT NULL REFERENCES automations(id) ON DELETE CASCADE,
  source_domain   TEXT NOT NULL,
  external_id     TEXT NOT NULL,
  url             TEXT NOT NULL,
  title           TEXT NOT NULL,
  raw_json        TEXT NOT NULL,
  score           REAL NOT NULL,
  matched_reasons TEXT,
  notified_at     INTEGER,
  created_at      INTEGER NOT NULL,
  UNIQUE(automation_id, external_id)
);
CREATE TABLE IF NOT EXISTS site_specs (
  domain            TEXT NOT NULL,
  vertical          TEXT NOT NULL,
  tier              TEXT NOT NULL,
  spec_json         TEXT NOT NULL,
  user_confirmed    INTEGER NOT NULL DEFAULT 0,
  last_validated_at INTEGER,
  success_rate      REAL,
  created_at        INTEGER NOT NULL,
  PRIMARY KEY (domain, vertical)
);
CREATE TABLE IF NOT EXISTS runs (
  id            TEXT PRIMARY KEY,
  automation_id TEXT NOT NULL REFERENCES automations(id) ON DELETE CASCADE,
  status        TEXT NOT NULL DEFAULT 'running',
  started_at    INTEGER NOT NULL,
  finished_at   INTEGER,
  items_seen    INTEGER DEFAULT 0,
  items_kept    INTEGER DEFAULT 0,
  errors_json   TEXT
);
CREATE TABLE IF NOT EXISTS run_logs (
  id         TEXT PRIMARY KEY,
  run_id     TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  level      TEXT NOT NULL,
  message    TEXT NOT NULL,
  created_at INTEGER NOT NULL
)
"""


@pytest.fixture
async def db(tmp_path):
    """Fresh SQLite DB with full schema; patches worker.db to use it."""
    db_file = str(tmp_path / "test.db")
    client = create_client(f"file:{db_file}")
    for stmt in [s.strip() for s in _SCHEMA.split(";") if s.strip()]:
        await client.execute(stmt)

    original = db_module._client
    db_module._client = client
    yield client
    db_module._client = original


# ── helpers ──────────────────────────────────────────────────────────────────

async def _insert_automation(
    client,
    auto_id: str = "auto-1",
    *,
    next_run_at: int | None = None,
    status: str = "active",
) -> None:
    now = int(time.time() * 1000)
    nra = next_run_at if next_run_at is not None else now - 1000
    from tests.python._libsql_stub import Statement

    await client.execute(
        Statement(
            """INSERT INTO automations
               (id, name, intent_text, vertical, spec_json, schedule_cron, status, next_run_at, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [auto_id, "Test", "Find jobs", "jobs", '{"sources":[]}', "0 * * * *", status, nra, now, now],
        )
    )


async def _insert_run(client, run_id: str = "run-1", auto_id: str = "auto-1") -> None:
    now = int(time.time() * 1000)
    from tests.python._libsql_stub import Statement

    await client.execute(
        Statement(
            "INSERT INTO runs (id, automation_id, status, started_at) VALUES (?, ?, 'running', ?)",
            [run_id, auto_id, now],
        )
    )


# ── fetch_due_automations ─────────────────────────────────────────────────────

async def test_fetch_due_returns_overdue_automation(db):
    await _insert_automation(db)  # next_run_at = now - 1000 (past)
    rows = await db_module.fetch_due_automations()
    assert len(rows) == 1
    assert rows[0]["id"] == "auto-1"


async def test_fetch_due_excludes_future_automation(db):
    now = int(time.time() * 1000)
    await _insert_automation(db, next_run_at=now + 60_000)
    rows = await db_module.fetch_due_automations()
    assert rows == []


async def test_fetch_due_excludes_paused_automation(db):
    await _insert_automation(db, status="paused")
    rows = await db_module.fetch_due_automations()
    assert rows == []


async def test_fetch_due_excludes_broken_automation(db):
    await _insert_automation(db, status="broken")
    rows = await db_module.fetch_due_automations()
    assert rows == []


# ── insert_run / finish_run ───────────────────────────────────────────────────

async def test_insert_run_creates_running_record(db):
    await _insert_automation(db)
    await db_module.insert_run("run-1", "auto-1")
    rs = await db.execute("SELECT status FROM runs WHERE id = 'run-1'")
    assert rs.rows[0][0] == "running"


async def test_finish_run_updates_to_success(db):
    await _insert_automation(db)
    await db_module.insert_run("run-1", "auto-1")
    await db_module.finish_run("run-1", status="success", items_seen=5, items_kept=2)
    rs = await db.execute("SELECT status, items_seen, items_kept FROM runs WHERE id = 'run-1'")
    row = rs.rows[0]
    assert row[0] == "success"
    assert row[1] == 5
    assert row[2] == 2


async def test_finish_run_stores_errors_json(db):
    await _insert_automation(db)
    await db_module.insert_run("run-1", "auto-1")
    await db_module.finish_run("run-1", status="error", errors=["timeout", "404"])
    rs = await db.execute("SELECT errors_json FROM runs WHERE id = 'run-1'")
    assert json.loads(rs.rows[0][0]) == ["timeout", "404"]


# ── append_run_log ─────────────────────────────────────────────────────────────

async def test_append_run_log_inserts_entry(db):
    await _insert_automation(db)
    await _insert_run(db)
    await db_module.append_run_log("run-1", "info", "Starting scrape")
    rs = await db.execute("SELECT level, message FROM run_logs WHERE run_id = 'run-1'")
    assert len(rs.rows) == 1
    assert rs.rows[0][0] == "info"
    assert rs.rows[0][1] == "Starting scrape"


async def test_append_run_log_multiple_entries(db):
    await _insert_automation(db)
    await _insert_run(db)
    await db_module.append_run_log("run-1", "info", "msg 1")
    await db_module.append_run_log("run-1", "error", "msg 2")
    rs = await db.execute("SELECT COUNT(*) FROM run_logs WHERE run_id = 'run-1'")
    assert rs.rows[0][0] == 2


# ── update_automation_schedule ─────────────────────────────────────────────────

async def test_update_schedule_sets_timestamps(db):
    await _insert_automation(db)
    now = int(time.time() * 1000)
    next_run = now + 3_600_000
    await db_module.update_automation_schedule("auto-1", last_run_at=now, next_run_at=next_run)
    rs = await db.execute("SELECT last_run_at, next_run_at FROM automations WHERE id = 'auto-1'")
    assert rs.rows[0][0] == now
    assert rs.rows[0][1] == next_run


# ── mark_automation_broken ─────────────────────────────────────────────────────

async def test_mark_broken_sets_status(db):
    await _insert_automation(db)
    await db_module.mark_automation_broken("auto-1")
    rs = await db.execute("SELECT status FROM automations WHERE id = 'auto-1'")
    assert rs.rows[0][0] == "broken"


# ── upsert_lead ───────────────────────────────────────────────────────────────

async def test_upsert_lead_returns_true_for_new(db):
    await _insert_automation(db)
    is_new = await db_module.upsert_lead(
        lead_id="lead-1",
        automation_id="auto-1",
        source_domain="example.com",
        external_id="ext-1",
        url="https://example.com/job/1",
        title="Software Engineer",
        raw_json={"id": "ext-1"},
        score=8.5,
    )
    assert is_new is True


async def test_upsert_lead_returns_false_for_duplicate(db):
    await _insert_automation(db)
    kwargs = dict(
        lead_id="lead-1",
        automation_id="auto-1",
        source_domain="example.com",
        external_id="ext-1",
        url="https://example.com/job/1",
        title="Software Engineer",
        raw_json={"id": "ext-1"},
        score=8.5,
    )
    await db_module.upsert_lead(**kwargs)
    is_new = await db_module.upsert_lead(**{**kwargs, "lead_id": "lead-2"})
    assert is_new is False


async def test_upsert_lead_stores_all_fields(db):
    await _insert_automation(db)
    await db_module.upsert_lead(
        lead_id="lead-1",
        automation_id="auto-1",
        source_domain="jobs.com",
        external_id="j99",
        url="https://jobs.com/99",
        title="Lead Engineer",
        raw_json={"id": "j99", "salary": "120k"},
        score=9.2,
        matched_reasons="Remote, Python",
    )
    rs = await db.execute("SELECT title, score, matched_reasons FROM leads WHERE id = 'lead-1'")
    row = rs.rows[0]
    assert row[0] == "Lead Engineer"
    assert row[1] == pytest.approx(9.2)
    assert row[2] == "Remote, Python"


# ── get_site_spec / upsert_site_spec ─────────────────────────────────────────

async def test_get_site_spec_returns_none_for_unknown(db):
    result = await db_module.get_site_spec("unknown.com", "jobs")
    assert result is None


async def test_upsert_and_get_site_spec_roundtrip(db):
    spec = {"endpoint": "https://api.example.com/jobs", "item_path": "jobs", "fields": {}}
    await db_module.upsert_site_spec("example.com", "jobs", "api", spec)
    row = await db_module.get_site_spec("example.com", "jobs")
    assert row is not None
    assert row["tier"] == "api"
    assert json.loads(row["spec_json"]) == spec
    assert row["user_confirmed"] == 0


async def test_upsert_site_spec_updates_on_conflict(db):
    spec_v1 = {"endpoint": "https://api.example.com/v1", "item_path": "", "fields": {}}
    spec_v2 = {"endpoint": "https://api.example.com/v2", "item_path": "data", "fields": {}}
    await db_module.upsert_site_spec("example.com", "jobs", "api", spec_v1)
    await db_module.upsert_site_spec("example.com", "jobs", "pydantic", spec_v2)
    row = await db_module.get_site_spec("example.com", "jobs")
    assert row["tier"] == "pydantic"
    assert json.loads(row["spec_json"]) == spec_v2

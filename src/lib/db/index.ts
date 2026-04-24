import { createClient, type Client } from "@libsql/client";
import fs from "fs";
import path from "path";

let client: Client;

function getClient(): Client {
  if (!client) {
    const isProduction = !!(
      process.env.TURSO_DATABASE_URL && process.env.TURSO_AUTH_TOKEN
    );

    if (isProduction) {
      client = createClient({
        url: process.env.TURSO_DATABASE_URL!,
        authToken: process.env.TURSO_AUTH_TOKEN!,
      });
    } else {
      const dbPath = process.env.DATABASE_PATH
        ? path.resolve(process.env.DATABASE_PATH)
        : path.join(process.cwd(), "data", "automations.db");
      fs.mkdirSync(path.dirname(dbPath), { recursive: true });
      client = createClient({ url: `file:${dbPath}` });
    }
  }
  return client;
}

export async function initDb() {
  const db = getClient();
  await db.executeMultiple(`
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
    );

    CREATE INDEX IF NOT EXISTS idx_leads_automation_id
      ON leads(automation_id);

    CREATE INDEX IF NOT EXISTS idx_runs_automation_id
      ON runs(automation_id);

    CREATE INDEX IF NOT EXISTS idx_run_logs_run_id
      ON run_logs(run_id);

    CREATE INDEX IF NOT EXISTS idx_automations_next_run
      ON automations(next_run_at, status);
  `);
}

export function db(): Client {
  return getClient();
}

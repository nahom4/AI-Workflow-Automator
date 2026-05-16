/**
 * Drops and recreates the automations table with the current schema.
 * Run once to fix a database created with an old schema version.
 *
 *   node scripts/migrate-db.mjs
 */
import { createClient } from "@libsql/client";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const dbPath = path.join(__dirname, "..", "data", "automations.db");

const client = createClient({ url: `file:${dbPath}` });

async function run() {
  console.log("DB:", dbPath);

  // Show current columns
  const info = await client.execute("PRAGMA table_info(automations)");
  console.log("Current columns:", info.rows.map((r) => r[1]).join(", "));

  // Recreate with correct schema (rename → create → copy → drop)
  await client.executeMultiple(`
    PRAGMA foreign_keys = OFF;

    CREATE TABLE automations_new (
      id              TEXT PRIMARY KEY,
      name            TEXT NOT NULL,
      intent_text     TEXT NOT NULL,
      vertical        TEXT NOT NULL DEFAULT 'other',
      spec_json       TEXT NOT NULL,
      schedule_cron   TEXT NOT NULL DEFAULT '0 */6 * * *',
      notify_email    TEXT,
      notify_whatsapp TEXT,
      status          TEXT NOT NULL DEFAULT 'active',
      last_run_at     INTEGER,
      next_run_at     INTEGER NOT NULL DEFAULT 0,
      created_at      INTEGER NOT NULL DEFAULT 0,
      updated_at      INTEGER NOT NULL DEFAULT 0
    );

    INSERT OR IGNORE INTO automations_new
      (id, name, intent_text, vertical, spec_json, status, next_run_at, created_at, updated_at)
    SELECT
      id,
      COALESCE(name, 'Untitled'),
      COALESCE(intent_text, ''),
      COALESCE(vertical, 'other'),
      COALESCE(spec_json, '{}'),
      COALESCE(status, 'active'),
      COALESCE(next_run_at, 0),
      COALESCE(created_at, 0),
      COALESCE(updated_at, 0)
    FROM automations;

    DROP TABLE automations;

    ALTER TABLE automations_new RENAME TO automations;

    CREATE INDEX IF NOT EXISTS idx_automations_next_run ON automations(next_run_at, status);

    PRAGMA foreign_keys = ON;
  `);

  const after = await client.execute("PRAGMA table_info(automations)");
  console.log("New columns:", after.rows.map((r) => r[1]).join(", "));
  console.log("Done.");
  await client.close();
}

run().catch((e) => { console.error(e); process.exit(1); });

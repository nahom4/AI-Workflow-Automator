import { createClient, type Client } from "@libsql/client";
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
      client = createClient({ url: `file:${dbPath}` });
    }
  }
  return client;
}

export async function initDb() {
  const db = getClient();
  await db.executeMultiple(`
    CREATE TABLE IF NOT EXISTS automations (
      id          TEXT PRIMARY KEY,
      name        TEXT NOT NULL,
      description TEXT NOT NULL,
      workflow    TEXT NOT NULL,
      webhook_url TEXT NOT NULL,
      created_at  INTEGER NOT NULL,
      updated_at  INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS executions (
      id              TEXT PRIMARY KEY,
      automation_id   TEXT NOT NULL REFERENCES automations(id) ON DELETE CASCADE,
      status          TEXT NOT NULL,
      trigger_payload TEXT NOT NULL,
      started_at      INTEGER NOT NULL,
      finished_at     INTEGER,
      error_message   TEXT
    );

    CREATE TABLE IF NOT EXISTS execution_logs (
      id            TEXT PRIMARY KEY,
      execution_id  TEXT NOT NULL REFERENCES executions(id) ON DELETE CASCADE,
      step_index    INTEGER NOT NULL,
      level         TEXT NOT NULL,
      message       TEXT NOT NULL,
      created_at    INTEGER NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_executions_automation_id
      ON executions(automation_id);

    CREATE INDEX IF NOT EXISTS idx_execution_logs_execution_id
      ON execution_logs(execution_id);
  `);
}

export function db(): Client {
  return getClient();
}

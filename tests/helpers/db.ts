import { createClient } from "@libsql/client";
import path from "path";

const TEST_DB_PATH = path.join(process.cwd(), "data", "test.db");

export function testDb() {
  return createClient({ url: `file:${TEST_DB_PATH}` });
}

export async function clearTables() {
  const client = testDb();
  // Silently ignore errors — tables may not exist on the very first run
  const tables = ["leads", "run_logs", "runs", "site_specs", "automations"];
  for (const table of tables) {
    await client.execute(`DELETE FROM ${table}`).catch(() => {});
  }
}

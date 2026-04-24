import { test, expect } from "@playwright/test";
import { testDb, clearTables } from "../helpers/db";

test.beforeEach(async () => {
  await clearTables();
});

test("new tables exist after initDb", async ({ request }) => {
  // Any API call triggers initDb()
  await request.get("/api/automations");

  const db = testDb();
  const result = await db.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
  );
  const names = result.rows.map((r) => r.name as string);

  expect(names).toContain("automations");
  expect(names).toContain("leads");
  expect(names).toContain("runs");
  expect(names).toContain("run_logs");
  expect(names).toContain("site_specs");
});

test("old tables are not present", async ({ request }) => {
  await request.get("/api/automations");

  const db = testDb();
  const result = await db.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
  );
  const names = result.rows.map((r) => r.name as string);

  expect(names).not.toContain("executions");
  expect(names).not.toContain("execution_logs");
});

test("automations table has new columns", async ({ request }) => {
  await request.get("/api/automations");

  const db = testDb();
  const result = await db.execute("PRAGMA table_info(automations)");
  const cols = result.rows.map((r) => r.name as string);

  expect(cols).toContain("intent_text");
  expect(cols).toContain("vertical");
  expect(cols).toContain("spec_json");
  expect(cols).toContain("schedule_cron");
  expect(cols).toContain("notify_email");
  expect(cols).toContain("notify_whatsapp");
  expect(cols).toContain("status");
  expect(cols).toContain("last_run_at");
  expect(cols).toContain("next_run_at");

  // Old columns must be gone
  expect(cols).not.toContain("description");
  expect(cols).not.toContain("workflow");
  expect(cols).not.toContain("webhook_url");
});

test("leads table has required columns", async ({ request }) => {
  await request.get("/api/automations");

  const db = testDb();
  const result = await db.execute("PRAGMA table_info(leads)");
  const cols = result.rows.map((r) => r.name as string);

  expect(cols).toContain("automation_id");
  expect(cols).toContain("source_domain");
  expect(cols).toContain("external_id");
  expect(cols).toContain("url");
  expect(cols).toContain("title");
  expect(cols).toContain("raw_json");
  expect(cols).toContain("score");
  expect(cols).toContain("matched_reasons");
  expect(cols).toContain("notified_at");
});

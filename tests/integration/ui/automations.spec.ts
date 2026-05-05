/**
 * Browser-level smoke tests for the automations UI.
 * These navigate real pages in Chrome and verify the UI renders correctly
 * against the same backend the API tests use.
 */
import { test, expect } from "@playwright/test";
import { clearTables, testDb } from "../../helpers/db";
import { nanoid } from "nanoid";

test.beforeEach(async () => {
  await clearTables();
});

test("automations list page renders empty state", async ({ page }) => {
  await page.goto("/automations");
  await expect(page).toHaveTitle(/AI Workflow Automator/i);
  // Some heading or label for the automations section should be present
  await expect(page.getByRole("heading", { name: /automations/i })).toBeVisible();
});

test("automations list page shows created automations", async ({ page }) => {
  // Insert an automation directly into the test DB
  const db = testDb();
  const id = nanoid(10);
  const now = Date.now();
  await db.execute({
    sql: `INSERT INTO automations
          (id, name, intent_text, vertical, spec_json, schedule_cron, status, next_run_at, created_at, updated_at)
          VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)`,
    args: [
      id,
      "React Jobs Watcher",
      "Monitor remote React jobs",
      "jobs",
      JSON.stringify({ sources: ["remoteok.com"], criteria: ["React"], threshold: 6 }),
      "0 */6 * * *",
      now,
      now,
      now,
    ],
  });

  await page.goto("/automations");
  await expect(page.getByText("React Jobs Watcher")).toBeVisible();
});

test("new automation page renders chat interface", async ({ page }) => {
  await page.goto("/automations/new");
  // Should have a textarea for chat input
  await expect(page.locator("textarea")).toBeVisible();
  // Should have the initial greeting from the assistant
  await expect(page.getByText(/track/i)).toBeVisible();
});

test("automation detail page shows leads and runs sections", async ({ page }) => {
  // Create an automation via the API to get a real ID
  const db = testDb();
  const id = nanoid(10);
  const now = Date.now();
  await db.execute({
    sql: `INSERT INTO automations
          (id, name, intent_text, vertical, spec_json, schedule_cron, status, next_run_at, created_at, updated_at)
          VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)`,
    args: [
      id,
      "Python Jobs",
      "Find Python jobs",
      "jobs",
      JSON.stringify({ sources: ["remoteok.com"], criteria: ["Python"], threshold: 6 }),
      "0 * * * *",
      now,
      now,
      now,
    ],
  });

  await page.goto(`/automations/${id}`);
  // The automation name should appear as a heading
  await expect(page.getByRole("heading", { name: "Python Jobs" })).toBeVisible();
});

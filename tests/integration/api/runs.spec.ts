import { test, expect } from "@playwright/test";
import { clearTables, testDb } from "../../helpers/db";
import { nanoid } from "nanoid";

const AUTOMATIONS = "/api/automations";

const automationPayload = {
  name: "Run Test Automation",
  intent_text: "Track Python jobs",
  vertical: "jobs",
  spec_json: { sources: ["remoteok.com"], criteria: ["Python"], threshold: 6 },
  schedule_cron: "0 * * * *",
};

test.beforeEach(async () => {
  await clearTables();
});

test("GET /api/automations/:id/runs returns empty array for new automation", async ({ request }) => {
  const create = await request.post(AUTOMATIONS, { data: automationPayload });
  const { id } = await create.json();

  const res = await request.get(`${AUTOMATIONS}/${id}/runs`);
  expect(res.status()).toBe(200);
  expect(await res.json()).toEqual([]);
});

test("GET /api/automations/:id/runs returns 404 for unknown automation", async ({ request }) => {
  const res = await request.get(`${AUTOMATIONS}/nonexistent/runs`);
  expect(res.status()).toBe(404);
});

test("GET /api/automations/:id/runs returns runs inserted by worker", async ({ request }) => {
  const create = await request.post(AUTOMATIONS, { data: automationPayload });
  const { id: automationId } = await create.json();

  const db = testDb();
  const runId = nanoid(10);
  const now = Date.now();
  await db.execute({
    sql: `INSERT INTO runs
            (id, automation_id, status, started_at, finished_at, items_seen, items_kept)
          VALUES (?, ?, ?, ?, ?, ?, ?)`,
    args: [runId, automationId, "success", now - 5000, now, 42, 7],
  });

  const res = await request.get(`${AUTOMATIONS}/${automationId}/runs`);
  expect(res.status()).toBe(200);

  const runs = await res.json();
  expect(runs).toHaveLength(1);
  expect(runs[0].id).toBe(runId);
  expect(runs[0].status).toBe("success");
  expect(runs[0].items_seen).toBe(42);
  expect(runs[0].items_kept).toBe(7);
});

test("GET /api/automations/:id/runs orders by started_at descending", async ({ request }) => {
  const create = await request.post(AUTOMATIONS, { data: automationPayload });
  const { id: automationId } = await create.json();

  const db = testDb();
  const now = Date.now();

  for (const [offset, status] of [
    [0, "success"],
    [10_000, "error"],
    [20_000, "success"],
  ]) {
    await db.execute({
      sql: `INSERT INTO runs (id, automation_id, status, started_at) VALUES (?, ?, ?, ?)`,
      args: [nanoid(10), automationId, status, now - (offset as number)],
    });
  }

  const res = await request.get(`${AUTOMATIONS}/${automationId}/runs`);
  const runs = await res.json();

  // Most recent first
  expect(runs[0].started_at).toBeGreaterThanOrEqual(runs[1].started_at as number);
  expect(runs[1].started_at).toBeGreaterThanOrEqual(runs[2].started_at as number);
});

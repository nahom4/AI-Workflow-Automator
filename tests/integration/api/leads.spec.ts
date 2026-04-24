import { test, expect } from "@playwright/test";
import { clearTables, testDb } from "../../helpers/db";
import { nanoid } from "nanoid";

const AUTOMATIONS = "/api/automations";

const automationPayload = {
  name: "Lead Test Automation",
  intent_text: "Find Python jobs",
  vertical: "jobs",
  spec_json: { sources: ["remoteok.com"], criteria: ["Python"], threshold: 6 },
  schedule_cron: "0 * * * *",
};

test.beforeEach(async () => {
  await clearTables();
});

test("GET /api/automations/:id/leads returns empty array for new automation", async ({ request }) => {
  const create = await request.post(AUTOMATIONS, { data: automationPayload });
  const { id } = await create.json();

  const res = await request.get(`${AUTOMATIONS}/${id}/leads`);
  expect(res.status()).toBe(200);
  expect(await res.json()).toEqual([]);
});

test("GET /api/automations/:id/leads returns 404 for unknown automation", async ({ request }) => {
  const res = await request.get(`${AUTOMATIONS}/nonexistent/leads`);
  expect(res.status()).toBe(404);
});

test("GET /api/automations/:id/leads returns leads inserted by worker", async ({ request }) => {
  const create = await request.post(AUTOMATIONS, { data: automationPayload });
  const { id: automationId } = await create.json();

  // Simulate the Python worker writing a lead directly to the DB
  const db = testDb();
  const leadId = nanoid(10);
  const now = Date.now();
  await db.execute({
    sql: `INSERT INTO leads
            (id, automation_id, source_domain, external_id, url, title, raw_json, score, created_at)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    args: [
      leadId,
      automationId,
      "remoteok.com",
      "rk-123",
      "https://remoteok.com/jobs/123",
      "Senior Python Engineer",
      JSON.stringify({ budget: "$120-150/hr" }),
      8.5,
      now,
    ],
  });

  const res = await request.get(`${AUTOMATIONS}/${automationId}/leads`);
  expect(res.status()).toBe(200);

  const leads = await res.json();
  expect(leads).toHaveLength(1);
  expect(leads[0].id).toBe(leadId);
  expect(leads[0].title).toBe("Senior Python Engineer");
  expect(leads[0].score).toBe(8.5);
  expect(leads[0].source_domain).toBe("remoteok.com");
});

test("GET /api/automations/:id/leads orders by score descending", async ({ request }) => {
  const create = await request.post(AUTOMATIONS, { data: automationPayload });
  const { id: automationId } = await create.json();

  const db = testDb();
  const now = Date.now();

  for (const [externalId, score, title] of [
    ["rk-1", 5.0, "Low Match"],
    ["rk-2", 9.0, "High Match"],
    ["rk-3", 7.0, "Mid Match"],
  ]) {
    await db.execute({
      sql: `INSERT INTO leads
              (id, automation_id, source_domain, external_id, url, title, raw_json, score, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      args: [nanoid(10), automationId, "remoteok.com", externalId, `https://remoteok.com/${externalId}`, title, "{}", score, now],
    });
  }

  const res = await request.get(`${AUTOMATIONS}/${automationId}/leads`);
  const leads = await res.json();
  expect(leads[0].title).toBe("High Match");
  expect(leads[1].title).toBe("Mid Match");
  expect(leads[2].title).toBe("Low Match");
});

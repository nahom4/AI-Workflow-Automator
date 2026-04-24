import { test, expect } from "@playwright/test";
import { clearTables } from "../../helpers/db";

const BASE = "/api/automations";

const validPayload = {
  name: "Test Job Hunt",
  intent_text: "Find senior React engineer jobs on RemoteOK",
  vertical: "jobs",
  spec_json: {
    sources: ["remoteok.com"],
    criteria: ["React", "senior", "remote"],
    threshold: 6,
  },
  schedule_cron: "0 */6 * * *",
  notify_email: "test@example.com",
};

test.beforeEach(async () => {
  await clearTables();
});

// ---------------------------------------------------------------------------
// POST
// ---------------------------------------------------------------------------

test("POST creates automation and returns new schema shape", async ({ request }) => {
  const res = await request.post(BASE, { data: validPayload });
  expect(res.status()).toBe(201);

  const body = await res.json();
  expect(body.id).toBeTruthy();
  expect(body.name).toBe(validPayload.name);
  expect(body.intent_text).toBe(validPayload.intent_text);
  expect(body.vertical).toBe("jobs");
  expect(body.status).toBe("active");
  expect(body.schedule_cron).toBe("0 */6 * * *");
  expect(body.notify_email).toBe("test@example.com");
  expect(typeof body.next_run_at).toBe("number");
  expect(typeof body.created_at).toBe("number");

  // Old fields must NOT be present
  expect(body.workflow).toBeUndefined();
  expect(body.webhook_url).toBeUndefined();
  expect(body.description).toBeUndefined();
});

test("POST rejects old schema (description + workflow)", async ({ request }) => {
  const res = await request.post(BASE, {
    data: { description: "old format", workflow: { name: "x", steps: [] } },
  });
  expect(res.status()).toBe(400);
});

test("POST rejects missing intent_text", async ({ request }) => {
  const res = await request.post(BASE, {
    data: { name: "no intent", spec_json: { sources: ["x.com"], criteria: [] }, schedule_cron: "0 * * * *" },
  });
  expect(res.status()).toBe(400);
});

test("POST rejects empty sources array", async ({ request }) => {
  const res = await request.post(BASE, {
    data: { ...validPayload, spec_json: { sources: [], criteria: [], threshold: 6 } },
  });
  expect(res.status()).toBe(400);
});

test("POST rejects invalid email", async ({ request }) => {
  const res = await request.post(BASE, {
    data: { ...validPayload, notify_email: "not-an-email" },
  });
  expect(res.status()).toBe(400);
});

test("POST defaults vertical to 'other' when omitted", async ({ request }) => {
  const { vertical: _, ...noVertical } = validPayload;
  const res = await request.post(BASE, { data: noVertical });
  expect(res.status()).toBe(201);
  expect((await res.json()).vertical).toBe("other");
});

// ---------------------------------------------------------------------------
// GET list
// ---------------------------------------------------------------------------

test("GET returns empty array initially", async ({ request }) => {
  const res = await request.get(BASE);
  expect(res.status()).toBe(200);
  expect(await res.json()).toEqual([]);
});

test("GET returns created automations with new schema fields", async ({ request }) => {
  await request.post(BASE, { data: validPayload });
  const res = await request.get(BASE);
  expect(res.status()).toBe(200);

  const rows = await res.json();
  expect(rows).toHaveLength(1);
  const row = rows[0];
  expect(row).toHaveProperty("intent_text");
  expect(row).toHaveProperty("spec_json");
  expect(row).toHaveProperty("status");
  expect(row).not.toHaveProperty("workflow");
  expect(row).not.toHaveProperty("webhook_url");
});

// ---------------------------------------------------------------------------
// GET single
// ---------------------------------------------------------------------------

test("GET /:id returns the automation", async ({ request }) => {
  const create = await request.post(BASE, { data: validPayload });
  const { id } = await create.json();

  const res = await request.get(`${BASE}/${id}`);
  expect(res.status()).toBe(200);
  expect((await res.json()).id).toBe(id);
});

test("GET /:id returns 404 for unknown id", async ({ request }) => {
  const res = await request.get(`${BASE}/nonexistent`);
  expect(res.status()).toBe(404);
});

// ---------------------------------------------------------------------------
// PATCH
// ---------------------------------------------------------------------------

test("PATCH /:id updates status to paused", async ({ request }) => {
  const create = await request.post(BASE, { data: validPayload });
  const { id } = await create.json();

  const res = await request.patch(`${BASE}/${id}`, { data: { status: "paused" } });
  expect(res.status()).toBe(200);
  expect((await res.json()).status).toBe("paused");
});

test("PATCH /:id rejects invalid status", async ({ request }) => {
  const create = await request.post(BASE, { data: validPayload });
  const { id } = await create.json();

  const res = await request.patch(`${BASE}/${id}`, { data: { status: "invalid" } });
  expect(res.status()).toBe(400);
});

test("PATCH /:id updates notify_email", async ({ request }) => {
  const create = await request.post(BASE, { data: validPayload });
  const { id } = await create.json();

  const res = await request.patch(`${BASE}/${id}`, { data: { notify_email: "new@example.com" } });
  expect(res.status()).toBe(200);
  expect((await res.json()).notify_email).toBe("new@example.com");
});

// ---------------------------------------------------------------------------
// DELETE
// ---------------------------------------------------------------------------

test("DELETE /:id removes the automation", async ({ request }) => {
  const create = await request.post(BASE, { data: validPayload });
  const { id } = await create.json();

  const del = await request.delete(`${BASE}/${id}`);
  expect(del.status()).toBe(204);

  const get = await request.get(`${BASE}/${id}`);
  expect(get.status()).toBe(404);
});

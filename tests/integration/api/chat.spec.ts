import { test, expect } from "@playwright/test";
import { clearTables } from "../../helpers/db";

const BASE = "/api/chat";

test.beforeEach(async () => {
  await clearTables();
});

test("POST with missing messages returns 400", async ({ request }) => {
  const res = await request.post(BASE, { data: {} });
  expect(res.status()).toBe(400);
});

test("POST with empty messages array returns 400", async ({ request }) => {
  const res = await request.post(BASE, { data: { messages: [] } });
  expect(res.status()).toBe(400);
});

test("POST with invalid role returns 400", async ({ request }) => {
  const res = await request.post(BASE, {
    data: { messages: [{ role: "system", content: "hi" }] },
  });
  expect(res.status()).toBe(400);
});

test("POST with invalid notify_email returns 400", async ({ request }) => {
  const res = await request.post(BASE, {
    data: {
      messages: [{ role: "user", content: "track jobs" }],
      notify_email: "not-an-email",
    },
  });
  expect(res.status()).toBe(400);
});

test("POST with valid messages returns 200 or 503", async ({ request }) => {
  // 503 when GROQ_API_KEY is absent (test env), 200 when Groq is reachable
  const res = await request.post(BASE, {
    data: { messages: [{ role: "user", content: "I want to track React jobs" }] },
  });
  expect([200, 503]).toContain(res.status());
  if (res.status() === 503) {
    const body = await res.json();
    expect(body.error).toMatch(/GROQ_API_KEY/i);
  }
  if (res.status() === 200) {
    const body = await res.json();
    expect(body).toHaveProperty("role", "assistant");
    expect(body).toHaveProperty("content");
    expect(typeof body.content).toBe("string");
  }
});

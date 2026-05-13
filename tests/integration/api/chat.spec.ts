import { test, expect } from "@playwright/test";
import { clearTables, testDb } from "../../helpers/db";

const BASE = "/api/chat";

test.beforeEach(async () => {
  await clearTables();
});

// --- Schema validation ---

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

test("messages with tool field are accepted by schema", async ({ request }) => {
  // Previously the schema didn't allow `tool`; this ensures it's accepted
  // without a 400. 200 requires Groq; 503 means key absent — both are valid here.
  const res = await request.post(BASE, {
    data: {
      messages: [
        { role: "user", content: "track React jobs" },
        {
          role: "assistant",
          content: "I suggest monitoring remoteok.com",
          tool: "suggest_sources",
        },
        { role: "user", content: "yes, create it" },
      ],
    },
  });
  expect([200, 503]).toContain(res.status());
});

// --- Live Groq tests (skipped when GROQ_API_KEY is absent) ---

test("single user message returns assistant response with role and content", async ({
  request,
}) => {
  test.skip(!process.env.GROQ_API_KEY, "GROQ_API_KEY not set");

  const res = await request.post(BASE, {
    data: { messages: [{ role: "user", content: "I want to track React jobs" }] },
  });
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body).toHaveProperty("role", "assistant");
  expect(typeof body.content).toBe("string");
  expect(body.content.length).toBeGreaterThan(0);
});

test("suggest_sources response includes tool and sources fields", async ({
  request,
}) => {
  test.skip(!process.env.GROQ_API_KEY, "GROQ_API_KEY not set");

  const res = await request.post(BASE, {
    data: { messages: [{ role: "user", content: "I want to monitor remote Python jobs" }] },
  });
  expect(res.status()).toBe(200);
  const body = await res.json();
  // Groq should call suggest_sources on a clear intent
  if (body.tool === "suggest_sources") {
    expect(Array.isArray(body.sources)).toBe(true);
    expect(body.sources.length).toBeGreaterThan(0);
    expect(body).toHaveProperty("vertical");
  }
  // If it returned plain text, that's also acceptable (LLM asked a clarifying Q)
  expect(body.role).toBe("assistant");
});

test("confirmation after suggest_sources triggers create_automation and writes to DB", async ({
  request,
}) => {
  // This is the exact scenario that the bug prevented from working.
  // The `tool` field on the assistant message must be forwarded so the API
  // forces tool_choice=create_automation on the confirmation turn.
  test.skip(!process.env.GROQ_API_KEY, "GROQ_API_KEY not set");

  const res = await request.post(BASE, {
    data: {
      messages: [
        { role: "user", content: "I want to monitor remote Python developer jobs" },
        {
          role: "assistant",
          content:
            "I suggest monitoring remoteok.com and weworkremotely.com for Python jobs.",
          tool: "suggest_sources",
        },
        { role: "user", content: "yes, create the automation" },
      ],
    },
  });

  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body.tool).toBe("create_automation");
  expect(typeof body.automation_id).toBe("string");
  expect(body.automation_id.length).toBeGreaterThan(0);

  // Verify the automation was actually written to the DB
  const db = testDb();
  const result = await db.execute({
    sql: "SELECT id, name, status FROM automations WHERE id = ?",
    args: [body.automation_id],
  });
  expect(result.rows.length).toBe(1);
  expect(result.rows[0][2]).toBe("active");
});

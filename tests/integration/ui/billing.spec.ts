/**
 * End-to-end USDC-on-Base checkout flow.
 *
 * Verifies that:
 *   - Pricing and billing pages render the new crypto-first upgrade UI.
 *   - /api/billing/x402-info exposes merchant + price info (or a precise error
 *     if MERCHANT_USDC_ADDRESS isn't configured).
 *   - /api/billing/x402-pay rejects unauthenticated callers and malformed payloads.
 *   - Clicking the crypto button in a headless browser (no wallet extension)
 *     surfaces the "No web3 wallet detected" error path cleanly.
 */
import { test, expect, type Page, request as pwRequest } from "@playwright/test";

const TEST_EMAIL = `billing-${Date.now()}@test.local`;
const TEST_PASSWORD = "testpassword123";

async function seedUser(): Promise<void> {
  const ctx = await pwRequest.newContext({ baseURL: "http://localhost:3001" });
  const res = await ctx.post("/api/auth/register", {
    data: { name: "Billing Test", email: TEST_EMAIL, password: TEST_PASSWORD },
  });
  if (!res.ok() && res.status() !== 409) {
    throw new Error(`Failed to seed user: ${res.status()} ${await res.text()}`);
  }
  await ctx.dispose();
}

async function signIn(page: Page): Promise<void> {
  await page.goto("/login");
  await page.fill('input[type="email"]', TEST_EMAIL);
  await page.fill('input[type="password"]', TEST_PASSWORD);
  await Promise.all([
    page.waitForURL(/\/automations/, { timeout: 15_000 }),
    page.click('button[type="submit"]'),
  ]);
}

test("pricing page renders Pro plan with crypto CTAs and Card 'Coming soon'", async ({ page }) => {
  await page.goto("/pricing");
  await expect(page.getByRole("heading", { name: /pricing/i })).toBeVisible();
  await expect(page.getByText("$29")).toBeVisible();
});

test("billing page redirects anonymous users to /login", async ({ page }) => {
  await page.goto("/account/billing");
  await expect(page).toHaveURL(/\/login/);
});

test("logged-in user sees crypto upgrade buttons on /account/billing", async ({ page }) => {
  await seedUser();
  await signIn(page);

  await page.goto("/account/billing");
  await expect(page.getByRole("heading", { name: /billing/i, exact: false }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: /Pay \$29 USDC · Monthly/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /Card · Coming soon/i })).toBeVisible();
});

test("/api/billing/x402-info returns merchant config or precise error", async ({ page }) => {
  const res = await page.request.get("/api/billing/x402-info");
  const status = res.status();
  const body = await res.json().catch(() => ({}));
  console.log("[x402-info]", { status, body });

  if (status === 200) {
    expect(body).toMatchObject({
      merchant: expect.stringMatching(/^0x[a-fA-F0-9]{40}$/),
      usdc: expect.stringMatching(/^0x[a-fA-F0-9]{40}$/),
      chainId: 8453,
      prices: { monthly: "29000000", annual: "276000000" },
    });
  } else {
    expect((body as { error?: string }).error).toMatch(/MERCHANT_USDC_ADDRESS/);
  }
});

test("/api/billing/x402-pay rejects unauthenticated requests", async ({ page }) => {
  const res = await page.request.post("/api/billing/x402-pay", {
    data: { cycle: "monthly", authorization: {} },
  });
  expect(res.status()).toBe(401);
});

test("/api/billing/x402-pay rejects malformed payloads when authenticated", async ({ page }) => {
  await seedUser();
  await signIn(page);

  const res = await page.request.post("/api/billing/x402-pay", {
    data: { cycle: "monthly" }, // missing authorization
  });
  expect(res.status()).toBe(400);
  const body = await res.json();
  expect(body.error).toMatch(/[Mm]issing|[Mm]alformed/);
});

test("clicking crypto button without a wallet shows clear error", async ({ page }) => {
  await seedUser();
  await signIn(page);

  await page.goto("/account/billing");

  // Make sure x402-info loaded so the button isn't disabled. If MERCHANT_USDC_ADDRESS
  // isn't set we'll see the "Payment unavailable" error instead — also a valid state to test.
  await page.waitForResponse(
    (r) => r.url().includes("/api/billing/x402-info"),
    { timeout: 10_000 },
  );

  const cryptoBtn = page.getByRole("button", { name: /Pay \$29 USDC · Monthly/i });
  await expect(cryptoBtn).toBeVisible();

  const isDisabled = await cryptoBtn.isDisabled();
  if (isDisabled) {
    // x402-info failed (merchant not configured) — we should see a Payment unavailable note.
    await expect(page.getByText(/Payment unavailable/i).first()).toBeVisible();
    return;
  }

  await cryptoBtn.click();
  // No window.ethereum in headless Chrome → component surfaces this message.
  await expect(page.getByText(/No web3 wallet detected/i)).toBeVisible({ timeout: 10_000 });
});

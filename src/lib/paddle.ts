/**
 * Paddle Billing API client.
 *
 * Uses Paddle's Transactions endpoint to generate hosted checkout URLs.
 * Configure these env vars before going live:
 *   PADDLE_API_KEY              — server-side key from Paddle dashboard
 *   PADDLE_ENV                  — "sandbox" or "production"
 *   PADDLE_PRICE_ID_PRO_MONTHLY — price ID for $29/mo plan
 *   PADDLE_PRICE_ID_PRO_ANNUAL  — price ID for $23/mo annual plan
 *   PADDLE_WEBHOOK_SECRET       — webhook signing secret
 *   NEXT_PUBLIC_APP_URL         — public origin used for return URLs
 */

const PADDLE_API_BASES = {
  sandbox: "https://sandbox-api.paddle.com",
  production: "https://api.paddle.com",
} as const;

function getApiBase(): string {
  const env = (process.env.PADDLE_ENV ?? "sandbox").toLowerCase();
  return env === "production" ? PADDLE_API_BASES.production : PADDLE_API_BASES.sandbox;
}

function requireApiKey(): string {
  const key = process.env.PADDLE_API_KEY;
  if (!key) throw new Error("PADDLE_API_KEY is not configured");
  return key;
}

export function getPriceIdForCycle(cycle: "monthly" | "annual"): string {
  const id =
    cycle === "annual"
      ? process.env.PADDLE_PRICE_ID_PRO_ANNUAL
      : process.env.PADDLE_PRICE_ID_PRO_MONTHLY;
  if (!id) {
    throw new Error(
      `Missing PADDLE_PRICE_ID_PRO_${cycle.toUpperCase()} env var — set it to the Paddle Price ID from your dashboard`,
    );
  }
  return id;
}

interface CreateTransactionParams {
  priceId: string;
  userId: string;
  userEmail: string;
  successUrl: string;
}

interface PaddleTransaction {
  id: string;
  checkout?: { url?: string | null } | null;
}

export async function createCheckoutTransaction(
  params: CreateTransactionParams,
): Promise<{ url: string; transactionId: string }> {
  const res = await fetch(`${getApiBase()}/transactions`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${requireApiKey()}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      items: [{ price_id: params.priceId, quantity: 1 }],
      customer: { email: params.userEmail },
      custom_data: { user_id: params.userId },
      checkout: { url: params.successUrl },
      collection_mode: "automatic",
    }),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Paddle transaction creation failed: ${res.status} ${text}`);
  }

  const body = (await res.json()) as { data?: PaddleTransaction };
  const url = body.data?.checkout?.url;
  const id = body.data?.id;
  if (!url || !id) {
    throw new Error("Paddle did not return a checkout URL");
  }
  return { url, transactionId: id };
}

/**
 * Verify a Paddle webhook signature.
 * Paddle sends the `Paddle-Signature` header in the form:
 *   ts=<unix-ms>;h1=<hex-hmac>
 * The signed payload is `<ts>:<raw-body>` using HMAC-SHA256 with the webhook secret.
 */
export async function verifyWebhookSignature(
  rawBody: string,
  signatureHeader: string | null,
): Promise<boolean> {
  const secret = process.env.PADDLE_WEBHOOK_SECRET;
  if (!secret) {
    console.error("PADDLE_WEBHOOK_SECRET is not configured");
    return false;
  }
  if (!signatureHeader) return false;

  const parts = Object.fromEntries(
    signatureHeader.split(";").map((p) => {
      const [k, v] = p.split("=");
      return [k?.trim(), v?.trim()];
    }),
  );
  const ts = parts.ts;
  const h1 = parts.h1;
  if (!ts || !h1) return false;

  const { createHmac, timingSafeEqual } = await import("crypto");
  const payload = `${ts}:${rawBody}`;
  const expected = createHmac("sha256", secret).update(payload).digest("hex");

  if (expected.length !== h1.length) return false;
  return timingSafeEqual(Buffer.from(expected, "hex"), Buffer.from(h1, "hex"));
}

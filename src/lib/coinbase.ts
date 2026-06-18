/**
 * Coinbase Commerce API client.
 *
 * Zero platform fees. Supports BTC, ETH, USDC, LTC, and more.
 * Configure these env vars:
 *   COINBASE_COMMERCE_API_KEY       — API key from Coinbase Commerce dashboard
 *   COINBASE_COMMERCE_WEBHOOK_SECRET — signing secret from your webhook endpoint
 *   NEXT_PUBLIC_APP_URL             — public origin used for redirect URLs
 */

const COINBASE_COMMERCE_API = "https://api.commerce.coinbase.com";

function requireApiKey(): string {
  const key = process.env.COINBASE_COMMERCE_API_KEY;
  if (!key) throw new Error("COINBASE_COMMERCE_API_KEY is not configured");
  return key;
}

interface CreateChargeParams {
  userId: string;
  cycle: "monthly" | "annual";
  redirectUrl: string;
  cancelUrl: string;
}

interface CoinbaseChargeResponse {
  data?: { id?: string; hosted_url?: string };
}

export async function createCryptoCharge(
  params: CreateChargeParams,
): Promise<{ url: string; chargeId: string }> {
  const amount = params.cycle === "annual" ? "276.00" : "29.00";
  const description =
    params.cycle === "annual"
      ? "Pro Plan — Annual ($23/mo × 12)"
      : "Pro Plan — Monthly";

  const res = await fetch(`${COINBASE_COMMERCE_API}/charges`, {
    method: "POST",
    headers: {
      "X-CC-Api-Key": requireApiKey(),
      "X-CC-Version": "2018-03-22",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      name: "AI Workflow Automator Pro",
      description,
      pricing_type: "fixed_price",
      local_price: { amount, currency: "USD" },
      metadata: { user_id: params.userId, cycle: params.cycle },
      redirect_url: params.redirectUrl,
      cancel_url: params.cancelUrl,
    }),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Coinbase Commerce charge creation failed: ${res.status} ${text}`);
  }

  const body = (await res.json()) as CoinbaseChargeResponse;
  const url = body.data?.hosted_url;
  const chargeId = body.data?.id;
  if (!url || !chargeId) throw new Error("Coinbase Commerce did not return a checkout URL");

  return { url, chargeId };
}

/**
 * Verify a Coinbase Commerce webhook signature.
 * The X-CC-Webhook-Signature header contains HMAC-SHA256(secret, rawBody) as hex.
 */
export async function verifyCryptoWebhookSignature(
  rawBody: string,
  signatureHeader: string | null,
): Promise<boolean> {
  const secret = process.env.COINBASE_COMMERCE_WEBHOOK_SECRET;
  if (!secret) {
    console.error("COINBASE_COMMERCE_WEBHOOK_SECRET is not configured");
    return false;
  }
  if (!signatureHeader) return false;

  const { createHmac, timingSafeEqual } = await import("crypto");
  const expected = createHmac("sha256", secret).update(rawBody).digest("hex");

  if (expected.length !== signatureHeader.length) return false;
  return timingSafeEqual(
    Buffer.from(expected, "hex"),
    Buffer.from(signatureHeader, "hex"),
  );
}

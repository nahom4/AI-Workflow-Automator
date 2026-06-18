import { NextRequest, NextResponse } from "next/server";
import { db, initDb } from "@/lib/db";
import { verifyCryptoWebhookSignature } from "@/lib/coinbase";

interface CoinbaseEvent {
  event?: {
    type?: string;
    data?: {
      metadata?: {
        user_id?: string;
        cycle?: string;
      };
    };
  };
}

const PERIOD_MS = {
  monthly: 30 * 24 * 60 * 60 * 1000,
  annual: 365 * 24 * 60 * 60 * 1000,
} as const;

export async function POST(req: NextRequest) {
  const raw = await req.text();
  const signature = req.headers.get("x-cc-webhook-signature");

  const valid = await verifyCryptoWebhookSignature(raw, signature);
  if (!valid) {
    return NextResponse.json({ error: "Invalid signature" }, { status: 401 });
  }

  let event: CoinbaseEvent;
  try {
    event = JSON.parse(raw) as CoinbaseEvent;
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const eventType = event.event?.type;
  const metadata = event.event?.data?.metadata;

  if (eventType === "charge:confirmed" || eventType === "charge:resolved") {
    const userId = metadata?.user_id;
    if (!userId) {
      console.warn("[billing/crypto-webhook] event missing metadata.user_id");
      return NextResponse.json({ ok: true });
    }

    const cycle = metadata?.cycle === "annual" ? "annual" : "monthly";
    const periodEnd = Date.now() + PERIOD_MS[cycle];

    await initDb();
    await db().execute({
      sql: `UPDATE users
              SET plan = 'pro',
                  subscription_status = 'active',
                  subscription_period_end = ?
            WHERE id = ?`,
      args: [periodEnd, userId],
    });
  }

  return NextResponse.json({ ok: true });
}

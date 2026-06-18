import { NextRequest, NextResponse } from "next/server";
import { db, initDb } from "@/lib/db";
import { verifyWebhookSignature } from "@/lib/paddle";

/**
 * Paddle webhook receiver.
 *
 * Subscribes to: subscription.created, subscription.updated, subscription.canceled,
 * transaction.completed. We map the customer back to our user via custom_data.user_id
 * that we set on transaction creation, then mirror status to the users table.
 */
export async function POST(req: NextRequest) {
  const raw = await req.text();
  const signature = req.headers.get("paddle-signature");

  const valid = await verifyWebhookSignature(raw, signature);
  if (!valid) {
    return NextResponse.json({ error: "Invalid signature" }, { status: 401 });
  }

  let event: PaddleEvent;
  try {
    event = JSON.parse(raw) as PaddleEvent;
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  await initDb();

  try {
    switch (event.event_type) {
      case "subscription.created":
      case "subscription.updated":
      case "subscription.activated":
        await applySubscriptionUpdate(event.data, { entitled: true });
        break;

      case "subscription.canceled":
      case "subscription.paused":
        await applySubscriptionUpdate(event.data, { entitled: false });
        break;

      case "transaction.completed":
        // Fallback path: ensures Pro flips on even if subscription.created arrives later.
        await applyTransactionCompleted(event.data);
        break;

      default:
        // Ignore other event types.
        break;
    }
  } catch (e) {
    console.error("[billing/webhook] handler error", e);
    return NextResponse.json({ error: "Handler error" }, { status: 500 });
  }

  return NextResponse.json({ ok: true });
}

interface PaddleEvent {
  event_type: string;
  data: PaddleSubscriptionData & PaddleTransactionData;
}

interface PaddleSubscriptionData {
  id?: string;
  status?: "active" | "past_due" | "paused" | "canceled" | "trialing";
  customer_id?: string;
  custom_data?: { user_id?: string } | null;
  current_billing_period?: { ends_at?: string } | null;
  next_billed_at?: string | null;
}

interface PaddleTransactionData {
  subscription_id?: string | null;
  customer_id?: string;
  custom_data?: { user_id?: string } | null;
  status?: string;
}

async function applySubscriptionUpdate(
  data: PaddleSubscriptionData,
  { entitled }: { entitled: boolean },
): Promise<void> {
  const userId = data.custom_data?.user_id;
  if (!userId) {
    console.warn("[billing/webhook] subscription event missing custom_data.user_id");
    return;
  }
  const subscriptionId = data.id ?? null;
  const customerId = data.customer_id ?? null;
  const status = data.status ?? (entitled ? "active" : "canceled");
  const endsAt = parsePaddleDate(
    data.current_billing_period?.ends_at ?? data.next_billed_at ?? null,
  );

  const plan = entitled ? "pro" : "free";

  await db().execute({
    sql: `UPDATE users
            SET plan = ?,
                paddle_customer_id = COALESCE(?, paddle_customer_id),
                paddle_subscription_id = COALESCE(?, paddle_subscription_id),
                subscription_status = ?,
                subscription_period_end = ?
          WHERE id = ?`,
    args: [plan, customerId, subscriptionId, status, endsAt, userId],
  });
}

async function applyTransactionCompleted(data: PaddleTransactionData): Promise<void> {
  const userId = data.custom_data?.user_id;
  if (!userId) return;
  // Only treat as a Pro flip if the transaction is tied to a subscription.
  if (!data.subscription_id) return;

  await db().execute({
    sql: `UPDATE users
            SET plan = 'pro',
                paddle_customer_id = COALESCE(?, paddle_customer_id),
                paddle_subscription_id = COALESCE(?, paddle_subscription_id),
                subscription_status = COALESCE(subscription_status, 'active')
          WHERE id = ?`,
    args: [data.customer_id ?? null, data.subscription_id, userId],
  });
}

function parsePaddleDate(s: string | null | undefined): number | null {
  if (!s) return null;
  const t = Date.parse(s);
  return isNaN(t) ? null : t;
}

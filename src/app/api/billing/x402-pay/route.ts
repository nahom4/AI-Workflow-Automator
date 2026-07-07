import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/auth";
import { db, initDb } from "@/lib/db";
import { relayAuthorization, type Cycle, type SignedAuthorization } from "@/lib/x402";

export const maxDuration = 90;

interface PayBody {
  cycle?: string;
  authorization?: SignedAuthorization;
}

export async function POST(req: NextRequest) {
  const session = await auth();
  const userId = session?.user?.id;
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = (await req.json().catch(() => ({}))) as PayBody;
  const cycle: Cycle = body.cycle === "annual" ? "annual" : "monthly";
  const a = body.authorization;

  if (!a || !a.from || !a.to || !a.value || !a.validAfter || !a.validBefore || !a.nonce || !a.signature) {
    return NextResponse.json({ error: "Missing or malformed authorization" }, { status: 400 });
  }

  try {
    const { txHash, periodEndMs } = await relayAuthorization(a, cycle);

    await initDb();
    await db().execute({
      sql: `UPDATE users
              SET plan = 'pro',
                  subscription_status = 'active',
                  subscription_period_end = ?
            WHERE id = ?`,
      args: [periodEndMs, userId],
    });

    return NextResponse.json({ ok: true, txHash, periodEndMs });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Payment relay failed";
    console.error("[billing/x402-pay]", msg);
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}

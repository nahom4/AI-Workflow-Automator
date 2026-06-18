import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/auth";
import { db, initDb } from "@/lib/db";
import { createCheckoutTransaction, getPriceIdForCycle } from "@/lib/paddle";
import { UserRow } from "@/types/db";

export async function POST(req: NextRequest) {
  const session = await auth();
  const userId = session?.user?.id;
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json().catch(() => ({}));
  const cycle: "monthly" | "annual" = body.cycle === "annual" ? "annual" : "monthly";

  await initDb();
  const result = await db().execute({
    sql: "SELECT email FROM users WHERE id = ?",
    args: [userId],
  });
  const user = result.rows[0] as unknown as Pick<UserRow, "email"> | undefined;
  if (!user) return NextResponse.json({ error: "User not found" }, { status: 404 });

  const origin =
    process.env.NEXT_PUBLIC_APP_URL ??
    req.headers.get("origin") ??
    new URL(req.url).origin;

  try {
    const priceId = getPriceIdForCycle(cycle);
    const { url } = await createCheckoutTransaction({
      priceId,
      userId,
      userEmail: user.email,
      successUrl: `${origin}/account/billing?checkout=success`,
    });
    return NextResponse.json({ url });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Checkout failed";
    console.error("[billing/checkout]", msg);
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}

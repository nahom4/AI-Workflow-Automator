import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/auth";
import { createCryptoCharge } from "@/lib/coinbase";

export async function POST(req: NextRequest) {
  const session = await auth();
  const userId = session?.user?.id;
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json().catch(() => ({}));
  const cycle: "monthly" | "annual" = body.cycle === "annual" ? "annual" : "monthly";

  const origin =
    process.env.NEXT_PUBLIC_APP_URL ??
    req.headers.get("origin") ??
    new URL(req.url).origin;

  try {
    const { url } = await createCryptoCharge({
      userId,
      cycle,
      redirectUrl: `${origin}/account/billing?checkout=success&method=crypto`,
      cancelUrl: `${origin}/pricing`,
    });
    return NextResponse.json({ url });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Checkout failed";
    console.error("[billing/crypto-checkout]", msg);
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}

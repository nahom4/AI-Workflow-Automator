import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/** Liveness probe — always 200 as long as the function can be served. */
export async function GET() {
  return NextResponse.json({ ok: true, ts: Date.now() });
}

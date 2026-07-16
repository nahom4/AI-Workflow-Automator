import { NextResponse } from "next/server";
import { db, initDb } from "@/lib/db";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

type Subsystem = { name: string; ok: boolean; detail?: string; latency_ms?: number };

/** Readiness probe — checks each downstream dependency and returns 503 if any
 * required subsystem is failing. Used by Vercel uptime monitors / external
 * probes that want a "can this thing actually serve traffic?" signal.
 */
export async function GET() {
  const checks: Subsystem[] = [];

  // 1. Turso reachability (round-trip on the libSQL connection)
  {
    const t0 = Date.now();
    try {
      await initDb();
      await db().execute("SELECT 1");
      checks.push({ name: "turso", ok: true, latency_ms: Date.now() - t0 });
    } catch (e) {
      checks.push({
        name: "turso", ok: false,
        detail: String(e).slice(0, 200), latency_ms: Date.now() - t0,
      });
    }
  }

  // 2. LLM provider keys present (not a live ping — those cost money and
  //    health probes can hit /ready every 30s).
  checks.push({
    name: "groq_keys",
    ok: !!(process.env.GROQ_API_KEYS || process.env.GROQ_API_KEY),
  });
  checks.push({
    name: "gemini_keys",
    ok: !!(process.env.GEMINI_API_KEYS || process.env.GEMINI_API_KEY),
  });

  // 3. Auth secret + Google OAuth client present (needed for any sign-in)
  checks.push({ name: "auth_secret", ok: !!process.env.AUTH_SECRET });
  checks.push({
    name: "google_oauth",
    ok: !!(process.env.GOOGLE_CLIENT_ID && process.env.GOOGLE_CLIENT_SECRET),
  });

  const required = new Set(["turso", "auth_secret"]);
  const failedRequired = checks.filter((c) => required.has(c.name) && !c.ok);
  const ok = failedRequired.length === 0;

  return NextResponse.json(
    { ok, ts: Date.now(), checks },
    { status: ok ? 200 : 503 },
  );
}

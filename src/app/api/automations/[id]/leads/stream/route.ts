import { NextRequest } from "next/server";
import { db, initDb } from "@/lib/db";
import { LeadRow } from "@/types/db";
import { auth } from "@/auth";

// Server-sent events: pushes new leads as they're inserted by the worker.
// Uses a small polling interval against the leads table (~1s) and emits
// only rows whose created_at is newer than the last seen tick.
//
// Wire format:
//   event: lead\n
//   data: {<LeadRow>}\n\n
//
//   event: ping\n
//   data: {"now": 1700000000000}\n\n   (every 15s — keeps proxies open)
//
//   event: done\n
//   data: {"reason": "run-finished"}\n\n  (when the active run finishes)

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const POLL_MS = 1000;
const PING_MS = 15000;
const MAX_DURATION_MS = 5 * 60 * 1000; // hard cap so a wedged stream doesn't leak

export async function GET(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const session = await auth();
  const userId = session?.user?.id;
  if (!userId) return new Response("unauthorized", { status: 401 });

  await initDb();

  const check = await db().execute({
    sql: "SELECT id FROM automations WHERE id = ? AND user_id = ?",
    args: [params.id, userId],
  });
  if (!check.rows[0]) {
    return new Response("not found", { status: 404 });
  }

  const since = Number(req.nextUrl.searchParams.get("since")) || Date.now();

  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      const enc = new TextEncoder();
      const send = (event: string, data: unknown) => {
        try {
          controller.enqueue(
            enc.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)
          );
        } catch {
          /* stream already closed */
        }
      };

      let lastSeen = since;
      let closed = false;
      const startedAt = Date.now();

      const close = () => {
        if (closed) return;
        closed = true;
        clearInterval(pollHandle);
        clearInterval(pingHandle);
        try {
          controller.close();
        } catch {
          /* already closed */
        }
      };

      req.signal.addEventListener("abort", close);

      const tick = async () => {
        if (closed) return;
        if (Date.now() - startedAt > MAX_DURATION_MS) {
          send("done", { reason: "max-duration" });
          close();
          return;
        }
        try {
          const r = await db().execute({
            sql: `SELECT * FROM leads
                  WHERE automation_id = ? AND created_at > ?
                  ORDER BY created_at ASC`,
            args: [params.id, lastSeen],
          });
          for (const row of r.rows as unknown as LeadRow[]) {
            send("lead", row);
            if (row.created_at > lastSeen) lastSeen = row.created_at;
          }

          // If no run is currently in 'running' status and we've sent at
          // least one tick, signal done so the client can stop reconnecting.
          const runStatus = await db().execute({
            sql: `SELECT status FROM runs
                  WHERE automation_id = ?
                  ORDER BY started_at DESC LIMIT 1`,
            args: [params.id],
          });
          const latest = runStatus.rows[0]?.status as string | undefined;
          if (latest && latest !== "running") {
            send("done", { reason: "run-finished", status: latest });
            close();
          }
        } catch (err) {
          send("error", { message: String(err) });
        }
      };

      const pollHandle = setInterval(tick, POLL_MS);
      const pingHandle = setInterval(
        () => send("ping", { now: Date.now() }),
        PING_MS
      );

      // Initial hello so the client knows the stream is open.
      send("hello", { since: lastSeen });
      // Run one tick right away so any leads created between page render
      // and stream open aren't missed.
      tick();
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no", // disable nginx buffering
    },
  });
}

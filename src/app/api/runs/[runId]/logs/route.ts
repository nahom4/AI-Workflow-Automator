import { NextRequest } from "next/server";
import { db, initDb } from "@/lib/db";
import { sseChannel } from "@/lib/sse";
import { auth } from "@/auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(
  req: NextRequest,
  { params }: { params: { runId: string } }
) {
  const session = await auth();
  const userId = session?.user?.id;
  if (!userId) return new Response("Unauthorized", { status: 401 });

  await initDb();

  const result = await db().execute({
    sql: `SELECT r.id, r.status FROM runs r
          JOIN automations a ON a.id = r.automation_id
          WHERE r.id = ? AND a.user_id = ?`,
    args: [params.runId, userId],
  });

  const run = result.rows[0];
  if (!run) {
    return new Response("Not found", { status: 404 });
  }

  const encoder = new TextEncoder();

  const stream = new ReadableStream({
    start(controller) {
      const send = (data: object) => {
        try {
          controller.enqueue(encoder.encode(`data: ${JSON.stringify(data)}\n\n`));
        } catch {
          // controller already closed
        }
      };

      // Already finished — replay from DB and close
      if (run.status !== "running") {
        db()
          .execute({
            sql: "SELECT * FROM run_logs WHERE run_id = ? ORDER BY created_at ASC",
            args: [params.runId],
          })
          .then((logsResult) => {
            logsResult.rows.forEach((row) => send({ ...row }));
            send({ type: "done", status: run.status });
            controller.close();
          });
        return;
      }

      // Live run — subscribe to in-process SSE channel keyed by runId
      const unsubscribe = sseChannel.subscribe(params.runId, (event) => {
        send(event);
        if (event.type === "done") {
          unsubscribe();
          controller.close();
        }
      });

      const pingInterval = setInterval(() => {
        try {
          controller.enqueue(encoder.encode(": ping\n\n"));
        } catch {
          clearInterval(pingInterval);
        }
      }, 15_000);

      req.signal.addEventListener("abort", () => {
        unsubscribe();
        clearInterval(pingInterval);
        try {
          controller.close();
        } catch {
          // already closed
        }
      });
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}

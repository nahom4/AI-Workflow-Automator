import { NextRequest } from "next/server";
import { db, initDb } from "@/lib/db";
import { sseChannel } from "@/lib/sse";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(
  req: NextRequest,
  { params }: { params: { executionId: string } }
) {
  await initDb();

  const result = await db().execute({
    sql: "SELECT id, status FROM executions WHERE id = ?",
    args: [params.executionId],
  });

  const execution = result.rows[0];
  if (!execution) {
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
      if (execution.status !== "running") {
        db()
          .execute({
            sql: "SELECT * FROM execution_logs WHERE execution_id = ? ORDER BY created_at ASC",
            args: [params.executionId],
          })
          .then((logsResult) => {
            logsResult.rows.forEach((row) => send({ ...row }));
            send({ type: "done", status: execution.status });
            controller.close();
          });
        return;
      }

      // Live execution — subscribe to in-process SSE channel
      const unsubscribe = sseChannel.subscribe(params.executionId, (event) => {
        send(event);
        if (event.stepIndex === -1 && event.level !== "info") {
          send({ type: "done", status: event.level === "success" ? "success" : "error" });
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
        try { controller.close(); } catch { /* already closed */ }
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

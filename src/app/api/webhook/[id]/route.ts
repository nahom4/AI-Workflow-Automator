import { NextRequest, NextResponse } from "next/server";
import { db, initDb } from "@/lib/db";
import { runExecution } from "@/lib/engine";
import { sseChannel } from "@/lib/sse";
import { nanoid } from "nanoid";
import { WorkflowDefinition } from "@/types/workflow";

export async function POST(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  await initDb();

  const automationResult = await db().execute({
    sql: "SELECT * FROM automations WHERE id = ?",
    args: [params.id],
  });

  const automation = automationResult.rows[0];
  if (!automation) {
    return NextResponse.json({ error: "Automation not found" }, { status: 404 });
  }

  const triggerPayload = await req.json().catch(() => ({}));
  const executionId = nanoid(10);
  const now = Date.now();

  await db().execute({
    sql: `INSERT INTO executions (id, automation_id, status, trigger_payload, started_at)
          VALUES (?, ?, 'running', ?, ?)`,
    args: [executionId, params.id, JSON.stringify(triggerPayload), now],
  });

  sseChannel.create(executionId);

  const workflow: WorkflowDefinition = JSON.parse(automation.workflow as string);

  // Fire-and-forget — runs in background
  runExecution(executionId, workflow, triggerPayload).catch(console.error);

  const logsUrl = `${process.env.NEXT_PUBLIC_APP_URL}/api/logs/${executionId}`;

  return NextResponse.json(
    { executionId, logsUrl, message: "Execution started" },
    { status: 202 }
  );
}

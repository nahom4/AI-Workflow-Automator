import { NextRequest, NextResponse } from "next/server";
import { db, initDb } from "@/lib/db";
import { nanoid } from "nanoid";
import { AutomationRow } from "@/types/db";
import { WorkflowDefinition } from "@/types/workflow";

async function ensureDb() {
  await initDb();
}

export async function GET() {
  await ensureDb();
  const result = await db().execute(
    "SELECT * FROM automations ORDER BY created_at DESC"
  );
  const rows = result.rows as unknown as AutomationRow[];
  return NextResponse.json(rows);
}

export async function POST(req: NextRequest) {
  await ensureDb();
  const body = await req.json().catch(() => null);
  const description: string = body?.description?.trim();
  const workflow: WorkflowDefinition = body?.workflow;

  if (!description || !workflow) {
    return NextResponse.json(
      { error: "description and workflow are required" },
      { status: 400 }
    );
  }

  const id = nanoid(10);
  const now = Date.now();
  const webhookUrl = `${process.env.NEXT_PUBLIC_APP_URL}/api/webhook/${id}`;

  await db().execute({
    sql: `INSERT INTO automations (id, name, description, workflow, webhook_url, created_at, updated_at)
          VALUES (?, ?, ?, ?, ?, ?, ?)`,
    args: [id, workflow.name, description, JSON.stringify(workflow), webhookUrl, now, now],
  });

  const result = await db().execute({
    sql: "SELECT * FROM automations WHERE id = ?",
    args: [id],
  });

  return NextResponse.json(result.rows[0], { status: 201 });
}

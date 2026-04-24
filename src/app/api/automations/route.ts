import { NextRequest, NextResponse } from "next/server";
import { db, initDb } from "@/lib/db";
import { createAutomationSchema } from "@/lib/validation";
import { nanoid } from "nanoid";

async function ensureDb() {
  await initDb();
}

export async function GET() {
  await ensureDb();
  const result = await db().execute(
    "SELECT * FROM automations ORDER BY created_at DESC"
  );
  return NextResponse.json(result.rows);
}

export async function POST(req: NextRequest) {
  await ensureDb();

  const body = await req.json().catch(() => null);
  const parsed = createAutomationSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: parsed.error.flatten() },
      { status: 400 }
    );
  }

  const {
    name,
    intent_text,
    vertical,
    spec_json,
    schedule_cron,
    notify_email,
    notify_whatsapp,
  } = parsed.data;

  const id = nanoid(10);
  const now = Date.now();

  await db().execute({
    sql: `INSERT INTO automations
            (id, name, intent_text, vertical, spec_json, schedule_cron,
             notify_email, notify_whatsapp, status, next_run_at, created_at, updated_at)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)`,
    args: [
      id,
      name,
      intent_text,
      vertical,
      JSON.stringify(spec_json),
      schedule_cron,
      notify_email ?? null,
      notify_whatsapp ?? null,
      now, // next_run_at = now → worker picks it up immediately
      now,
      now,
    ],
  });

  const result = await db().execute({
    sql: "SELECT * FROM automations WHERE id = ?",
    args: [id],
  });

  return NextResponse.json(result.rows[0], { status: 201 });
}

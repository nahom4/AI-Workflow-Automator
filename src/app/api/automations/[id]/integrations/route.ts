import { NextRequest, NextResponse } from "next/server";
import { db, initDb } from "@/lib/db";
import { auth } from "@/auth";
import { z } from "zod";

const schema = z.object({
  google_sheet_id: z.string().optional(),
  notify_gmail: z.boolean().optional(),
});

export async function PATCH(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const session = await auth();
  const userId = session?.user?.id;
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  await initDb();
  const existing = await db().execute({
    sql: "SELECT id FROM automations WHERE id = ? AND user_id = ?",
    args: [params.id, userId],
  });
  if (!existing.rows[0]) return NextResponse.json({ error: "Not found" }, { status: 404 });

  const body = await req.json().catch(() => null);
  const parsed = schema.safeParse(body);
  if (!parsed.success) return NextResponse.json({ error: parsed.error.flatten() }, { status: 400 });

  const { google_sheet_id, notify_gmail } = parsed.data;
  const now = Date.now();

  if (google_sheet_id !== undefined) {
    await db().execute({
      sql: "UPDATE automations SET google_sheet_id = ?, updated_at = ? WHERE id = ?",
      args: [google_sheet_id || null, now, params.id],
    });
  }
  if (notify_gmail !== undefined) {
    await db().execute({
      sql: "UPDATE automations SET notify_gmail = ?, updated_at = ? WHERE id = ?",
      args: [notify_gmail ? 1 : 0, now, params.id],
    });
  }

  const result = await db().execute({
    sql: "SELECT * FROM automations WHERE id = ?",
    args: [params.id],
  });
  return NextResponse.json(result.rows[0]);
}

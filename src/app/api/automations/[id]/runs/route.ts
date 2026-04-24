import { NextRequest, NextResponse } from "next/server";
import { db, initDb } from "@/lib/db";

export async function GET(
  _req: NextRequest,
  { params }: { params: { id: string } }
) {
  await initDb();

  // Verify automation exists
  const check = await db().execute({
    sql: "SELECT id FROM automations WHERE id = ?",
    args: [params.id],
  });
  if (!check.rows[0]) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const result = await db().execute({
    sql: "SELECT * FROM runs WHERE automation_id = ? ORDER BY started_at DESC LIMIT 50",
    args: [params.id],
  });

  return NextResponse.json(result.rows);
}

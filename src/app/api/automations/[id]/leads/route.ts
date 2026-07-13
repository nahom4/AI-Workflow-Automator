import { NextRequest, NextResponse } from "next/server";
import { db, initDb } from "@/lib/db";
import { auth } from "@/auth";

export async function GET(
  _req: NextRequest,
  { params }: { params: { id: string } }
) {
  const session = await auth();
  const userId = session?.user?.id;
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  await initDb();

  const check = await db().execute({
    sql: "SELECT id FROM automations WHERE id = ? AND user_id = ?",
    args: [params.id, userId],
  });
  if (!check.rows[0]) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const result = await db().execute({
    sql: "SELECT * FROM leads WHERE automation_id = ? ORDER BY score DESC, created_at DESC",
    args: [params.id],
  });

  return NextResponse.json(result.rows);
}

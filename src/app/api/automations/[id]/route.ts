import { NextRequest, NextResponse } from "next/server";
import { db, initDb } from "@/lib/db";

export async function GET(
  _req: NextRequest,
  { params }: { params: { id: string } }
) {
  await initDb();
  const result = await db().execute({
    sql: "SELECT * FROM automations WHERE id = ?",
    args: [params.id],
  });

  if (!result.rows[0]) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  return NextResponse.json(result.rows[0]);
}

export async function DELETE(
  _req: NextRequest,
  { params }: { params: { id: string } }
) {
  await initDb();
  await db().execute({
    sql: "DELETE FROM automations WHERE id = ?",
    args: [params.id],
  });
  return new NextResponse(null, { status: 204 });
}

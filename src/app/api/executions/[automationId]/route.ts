import { NextRequest, NextResponse } from "next/server";
import { db, initDb } from "@/lib/db";

export async function GET(
  _req: NextRequest,
  { params }: { params: { automationId: string } }
) {
  await initDb();
  const result = await db().execute({
    sql: "SELECT * FROM executions WHERE automation_id = ? ORDER BY started_at DESC",
    args: [params.automationId],
  });
  return NextResponse.json(result.rows);
}

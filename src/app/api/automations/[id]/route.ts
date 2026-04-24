import { NextRequest, NextResponse } from "next/server";
import { db, initDb } from "@/lib/db";
import { updateAutomationSchema } from "@/lib/validation";

async function ensureDb() {
  await initDb();
}

export async function GET(
  _req: NextRequest,
  { params }: { params: { id: string } }
) {
  await ensureDb();
  const result = await db().execute({
    sql: "SELECT * FROM automations WHERE id = ?",
    args: [params.id],
  });
  if (!result.rows[0]) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }
  return NextResponse.json(result.rows[0]);
}

export async function PATCH(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  await ensureDb();

  const body = await req.json().catch(() => null);
  const parsed = updateAutomationSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: parsed.error.flatten() },
      { status: 400 }
    );
  }

  const updates = parsed.data;
  const fields = Object.keys(updates).filter(
    (k) => updates[k as keyof typeof updates] !== undefined
  );

  if (fields.length === 0) {
    return NextResponse.json({ error: "No fields to update" }, { status: 400 });
  }

  const now = Date.now();
  const setClauses = [...fields.map((f) => `${f} = ?`), "updated_at = ?"].join(", ");
  const args = [
    ...fields.map((f) => updates[f as keyof typeof updates] ?? null),
    now,
    params.id,
  ];

  await db().execute({
    sql: `UPDATE automations SET ${setClauses} WHERE id = ?`,
    args,
  });

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
  await ensureDb();
  await db().execute({
    sql: "DELETE FROM automations WHERE id = ?",
    args: [params.id],
  });
  return new NextResponse(null, { status: 204 });
}

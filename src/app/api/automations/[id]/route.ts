import { NextRequest, NextResponse } from "next/server";
import { db, initDb } from "@/lib/db";
import { updateAutomationSchema } from "@/lib/validation";
import { auth } from "@/auth";

async function getUserId(): Promise<string | null> {
  const session = await auth();
  return session?.user?.id ?? null;
}

async function ownedAutomation(id: string, userId: string) {
  await initDb();
  const result = await db().execute({
    sql: "SELECT * FROM automations WHERE id = ? AND user_id = ?",
    args: [id, userId],
  });
  return result.rows[0] ?? null;
}

export async function GET(
  _req: NextRequest,
  { params }: { params: { id: string } }
) {
  const userId = await getUserId();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const row = await ownedAutomation(params.id, userId);
  if (!row) return NextResponse.json({ error: "Not found" }, { status: 404 });
  return NextResponse.json(row);
}

export async function PATCH(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const userId = await getUserId();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const existing = await ownedAutomation(params.id, userId);
  if (!existing) return NextResponse.json({ error: "Not found" }, { status: 404 });

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
  const userId = await getUserId();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const existing = await ownedAutomation(params.id, userId);
  if (!existing) return NextResponse.json({ error: "Not found" }, { status: 404 });

  await db().execute({
    sql: "DELETE FROM automations WHERE id = ? AND user_id = ?",
    args: [params.id, userId],
  });
  return new NextResponse(null, { status: 204 });
}

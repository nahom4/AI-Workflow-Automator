import { NextRequest, NextResponse } from "next/server";
import { db, initDb } from "@/lib/db";
import { auth } from "@/auth";
import { AutomationRow, LeadRow, UserRow } from "@/types/db";

async function refreshAccessToken(refreshToken: string): Promise<{ access_token: string; expires_at: number } | null> {
  const res = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "refresh_token",
      refresh_token: refreshToken,
      client_id: process.env.GOOGLE_CLIENT_ID!,
      client_secret: process.env.GOOGLE_CLIENT_SECRET!,
    }),
  });
  if (!res.ok) return null;
  const data = await res.json() as { access_token: string; expires_in: number };
  return { access_token: data.access_token, expires_at: Date.now() + data.expires_in * 1000 };
}

async function getValidToken(userId: string, user: Pick<UserRow, "google_access_token" | "google_refresh_token" | "google_token_expiry">): Promise<string | null> {
  if (!user.google_access_token) return null;
  if ((user.google_token_expiry ?? 0) - Date.now() > 5 * 60 * 1000) return user.google_access_token;
  if (!user.google_refresh_token) return null;
  const refreshed = await refreshAccessToken(user.google_refresh_token);
  if (!refreshed) return null;
  await db().execute({
    sql: "UPDATE users SET google_access_token = ?, google_token_expiry = ? WHERE id = ?",
    args: [refreshed.access_token, refreshed.expires_at, userId],
  });
  return refreshed.access_token;
}

// POST /api/automations/[id]/integrations/sheets/sync
export async function POST(
  _req: NextRequest,
  { params }: { params: { id: string } }
) {
  const session = await auth();
  const userId = session?.user?.id;
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  await initDb();

  const [autoRes, userRes, leadsRes] = await Promise.all([
    db().execute({
      sql: "SELECT * FROM automations WHERE id = ? AND (user_id = ? OR user_id IS NULL)",
      args: [params.id, userId],
    }),
    db().execute({
      sql: "SELECT google_access_token, google_refresh_token, google_token_expiry FROM users WHERE id = ?",
      args: [userId],
    }),
    db().execute({
      sql: "SELECT * FROM leads WHERE automation_id = ? ORDER BY created_at ASC",
      args: [params.id],
    }),
  ]);

  const automation = autoRes.rows[0] as unknown as AutomationRow | undefined;
  if (!automation) return NextResponse.json({ error: "Not found" }, { status: 404 });

  const sheetId = automation.google_sheet_id;
  if (!sheetId) return NextResponse.json({ error: "No spreadsheet connected" }, { status: 400 });

  const user = userRes.rows[0] as unknown as Pick<UserRow, "google_access_token" | "google_refresh_token" | "google_token_expiry"> | undefined;
  const token = user ? await getValidToken(userId, user) : null;
  if (!token) return NextResponse.json({ error: "No Google token" }, { status: 403 });

  const leads = leadsRes.rows as unknown as LeadRow[];
  if (leads.length === 0) return NextResponse.json({ synced: 0 });

  const rows = leads.map((l) => [
    l.title,
    l.url,
    String(Math.round(l.score * 10) / 10),
    l.matched_reasons ?? "",
    l.source_domain,
    new Date(l.created_at).toISOString(),
  ]);

  // Clear sheet content below header, then append all leads
  await fetch(
    `https://sheets.googleapis.com/v4/spreadsheets/${sheetId}/values/A2:F?clear=true`,
    { method: "POST", headers: { Authorization: `Bearer ${token}` } }
  );

  const appendRes = await fetch(
    `https://sheets.googleapis.com/v4/spreadsheets/${sheetId}/values/A1:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ values: rows }),
    }
  );

  if (!appendRes.ok) {
    const err = await appendRes.text();
    return NextResponse.json({ error: err.slice(0, 200) }, { status: 502 });
  }

  return NextResponse.json({ synced: rows.length });
}

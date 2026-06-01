import { NextRequest, NextResponse } from "next/server";
import { db, initDb } from "@/lib/db";
import { auth } from "@/auth";
import { AutomationRow, UserRow } from "@/types/db";

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
  return {
    access_token: data.access_token,
    expires_at: Date.now() + data.expires_in * 1000,
  };
}

async function getValidToken(user: Pick<UserRow, "id" | "google_access_token" | "google_refresh_token" | "google_token_expiry">): Promise<string | null> {
  if (!user.google_access_token) return null;

  const fiveMin = 5 * 60 * 1000;
  const expiry = user.google_token_expiry ?? 0;
  if (expiry - Date.now() > fiveMin) return user.google_access_token;

  if (!user.google_refresh_token) return null;
  const refreshed = await refreshAccessToken(user.google_refresh_token);
  if (!refreshed) return null;

  await db().execute({
    sql: "UPDATE users SET google_access_token = ?, google_token_expiry = ? WHERE id = ?",
    args: [refreshed.access_token, refreshed.expires_at, user.id],
  });
  return refreshed.access_token;
}

// POST /api/automations/[id]/integrations/sheets — create a new spreadsheet
export async function POST(
  _req: NextRequest,
  { params }: { params: { id: string } }
) {
  const session = await auth();
  const userId = session?.user?.id;
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  await initDb();

  const [autoRes, userRes] = await Promise.all([
    db().execute({ sql: "SELECT * FROM automations WHERE id = ? AND user_id = ?", args: [params.id, userId] }),
    db().execute({ sql: "SELECT id, google_access_token, google_refresh_token, google_token_expiry FROM users WHERE id = ?", args: [userId] }),
  ]);

  const automation = autoRes.rows[0] as unknown as AutomationRow | undefined;
  if (!automation) return NextResponse.json({ error: "Not found" }, { status: 404 });

  const user = userRes.rows[0] as unknown as Pick<UserRow, "id" | "google_access_token" | "google_refresh_token" | "google_token_expiry"> | undefined;
  const token = user ? await getValidToken({ ...user, id: userId }) : null;
  if (!token) return NextResponse.json({ error: "No Google token — sign in with Google first" }, { status: 403 });

  // Create the spreadsheet
  const createRes = await fetch("https://sheets.googleapis.com/v4/spreadsheets", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      properties: { title: `${automation.name} — Leads` },
      sheets: [{ properties: { title: "Leads" } }],
    }),
  });

  if (!createRes.ok) {
    const err = await createRes.text();
    return NextResponse.json({ error: `Sheets API error: ${err.slice(0, 200)}` }, { status: 502 });
  }

  const sheet = await createRes.json() as { spreadsheetId: string; spreadsheetUrl: string };

  // Write header row
  await fetch(
    `https://sheets.googleapis.com/v4/spreadsheets/${sheet.spreadsheetId}/values/A1:append?valueInputOption=RAW`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ values: [["Title", "URL", "Score", "Reasons", "Source", "Found at"]] }),
    }
  );

  // Save sheet ID to automation
  await db().execute({
    sql: "UPDATE automations SET google_sheet_id = ?, updated_at = ? WHERE id = ?",
    args: [sheet.spreadsheetId, Date.now(), params.id],
  });

  return NextResponse.json({ sheet_id: sheet.spreadsheetId, sheet_url: sheet.spreadsheetUrl });
}

// DELETE /api/automations/[id]/integrations/sheets — disconnect the sheet
export async function DELETE(
  _req: NextRequest,
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

  await db().execute({
    sql: "UPDATE automations SET google_sheet_id = NULL, updated_at = ? WHERE id = ?",
    args: [Date.now(), params.id],
  });
  return new NextResponse(null, { status: 204 });
}

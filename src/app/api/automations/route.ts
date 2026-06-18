import { NextRequest, NextResponse } from "next/server";
import { db, initDb } from "@/lib/db";
import { createAutomationSchema } from "@/lib/validation";
import { nanoid } from "nanoid";
import { auth } from "@/auth";
import { getUserPlan, countUserAutomations, cronMinIntervalHours } from "@/lib/plans";

async function getUserId(): Promise<string | null> {
  const session = await auth();
  return session?.user?.id ?? null;
}

export async function GET() {
  const userId = await getUserId();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  await initDb();
  const result = await db().execute({
    sql: "SELECT * FROM automations WHERE user_id = ? ORDER BY created_at DESC",
    args: [userId],
  });
  return NextResponse.json(result.rows);
}

export async function POST(req: NextRequest) {
  const userId = await getUserId();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  await initDb();

  const body = await req.json().catch(() => null);
  const parsed = createAutomationSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.flatten() }, { status: 400 });
  }

  const { name, intent_text, vertical, spec_json, schedule_cron, notify_email, notify_whatsapp } =
    parsed.data;

  const plan = await getUserPlan(userId);

  const currentCount = await countUserAutomations(userId);
  if (currentCount >= plan.maxAutomations) {
    return NextResponse.json(
      {
        error: `You've reached your plan limit of ${plan.maxAutomations} automations. Upgrade to Pro for up to 15.`,
        code: "PLAN_LIMIT_AUTOMATIONS",
      },
      { status: 402 },
    );
  }

  const intervalHours = cronMinIntervalHours(schedule_cron);
  if (intervalHours < plan.minScheduleHours) {
    return NextResponse.json(
      {
        error: `Your plan only allows runs every ${plan.minScheduleHours} hours or longer. Upgrade to Pro for more frequent runs.`,
        code: "PLAN_LIMIT_FREQUENCY",
      },
      { status: 402 },
    );
  }

  const specCriteria = Array.isArray((spec_json as { criteria?: unknown[] }).criteria)
    ? ((spec_json as { criteria?: unknown[] }).criteria as unknown[]).length
    : 0;
  if (specCriteria > plan.maxCriteriaPerAutomation) {
    return NextResponse.json(
      {
        error: `Your plan allows up to ${plan.maxCriteriaPerAutomation} criteria per automation. Upgrade to Pro for more.`,
        code: "PLAN_LIMIT_CRITERIA",
      },
      { status: 402 },
    );
  }

  const specSources = Array.isArray((spec_json as { sources?: unknown[] }).sources)
    ? ((spec_json as { sources?: unknown[] }).sources as unknown[]).length
    : 0;
  if (specSources > plan.maxSourcesPerAutomation) {
    return NextResponse.json(
      {
        error: `Your plan allows up to ${plan.maxSourcesPerAutomation} sources per automation. Upgrade to Pro for more.`,
        code: "PLAN_LIMIT_SOURCES",
      },
      { status: 402 },
    );
  }

  const id = nanoid(10);
  const now = Date.now();

  await db().execute({
    sql: `INSERT INTO automations
            (id, name, intent_text, vertical, spec_json, schedule_cron,
             notify_email, notify_whatsapp, status, next_run_at, created_at, updated_at, user_id)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)`,
    args: [
      id, name, intent_text, vertical, JSON.stringify(spec_json), schedule_cron,
      notify_email ?? null, notify_whatsapp ?? null,
      now, now, now, userId,
    ],
  });

  const result = await db().execute({
    sql: "SELECT * FROM automations WHERE id = ?",
    args: [id],
  });
  return NextResponse.json(result.rows[0], { status: 201 });
}

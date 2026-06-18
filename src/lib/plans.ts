import { db, initDb } from "@/lib/db";
import { UserRow } from "@/types/db";

export type PlanId = "free" | "pro";

export interface PlanLimits {
  id: PlanId;
  name: string;
  priceMonthly: number;
  priceAnnualMonthly: number;
  maxAutomations: number;
  maxCriteriaPerAutomation: number;
  maxSourcesPerAutomation: number;
  minScheduleHours: number;
  leadHistoryDays: number;
  rankerTier: "base" | "advanced";
  cvAwareRanking: boolean;
  integrations: {
    email: boolean;
    gmail: boolean;
    googleSheets: boolean;
  };
}

export const PLANS: Record<PlanId, PlanLimits> = {
  free: {
    id: "free",
    name: "Free",
    priceMonthly: 0,
    priceAnnualMonthly: 0,
    maxAutomations: 3,
    maxCriteriaPerAutomation: 3,
    maxSourcesPerAutomation: 3,
    minScheduleHours: 24,
    leadHistoryDays: 7,
    rankerTier: "base",
    cvAwareRanking: false,
    integrations: {
      email: true,
      gmail: false,
      googleSheets: false,
    },
  },
  pro: {
    id: "pro",
    name: "Pro",
    priceMonthly: 29,
    priceAnnualMonthly: 23,
    maxAutomations: 15,
    maxCriteriaPerAutomation: 10,
    maxSourcesPerAutomation: 10,
    minScheduleHours: 2,
    leadHistoryDays: 90,
    rankerTier: "advanced",
    cvAwareRanking: true,
    integrations: {
      email: true,
      gmail: true,
      googleSheets: true,
    },
  },
};

export function getPlan(id: PlanId | string | null | undefined): PlanLimits {
  if (id === "pro") return PLANS.pro;
  return PLANS.free;
}

export async function getUserPlan(userId: string): Promise<PlanLimits> {
  await initDb();
  const result = await db().execute({
    sql: "SELECT plan, subscription_status, subscription_period_end FROM users WHERE id = ?",
    args: [userId],
  });
  const row = result.rows[0] as unknown as
    | Pick<UserRow, "plan" | "subscription_status" | "subscription_period_end">
    | undefined;

  if (!row) return PLANS.free;

  // Pro requires an active or past-due subscription that hasn't fully lapsed.
  if (row.plan === "pro") {
    const status = row.subscription_status;
    const stillEntitled = status === "active" || status === "past_due";
    if (stillEntitled) return PLANS.pro;
  }
  return PLANS.free;
}

export async function countUserAutomations(userId: string): Promise<number> {
  await initDb();
  const result = await db().execute({
    sql: "SELECT COUNT(*) as c FROM automations WHERE user_id = ?",
    args: [userId],
  });
  return Number(result.rows[0]?.c ?? 0);
}

export function cronMinIntervalHours(cron: string): number {
  // Parse a 5-field cron and return the minimum interval in hours.
  // Supports "0 */N * * *" patterns and basic minute/hour combinations.
  const parts = cron.trim().split(/\s+/);
  if (parts.length < 5) return 24;
  const [minute, hour] = parts;

  // Hour step: "*/N"
  const hourStep = /^\*\/(\d+)$/.exec(hour);
  if (hourStep) return Math.max(1, parseInt(hourStep[1], 10));

  // Single specific hour like "9" → daily
  if (/^\d+$/.test(hour)) return 24;

  // Multiple hours comma-separated like "9,17" → assume 8h gap minimum
  if (hour.includes(",")) {
    const hours = hour.split(",").map((h) => parseInt(h, 10)).filter((h) => !isNaN(h)).sort((a, b) => a - b);
    if (hours.length >= 2) {
      let minGap = 24;
      for (let i = 1; i < hours.length; i++) minGap = Math.min(minGap, hours[i] - hours[i - 1]);
      minGap = Math.min(minGap, 24 - hours[hours.length - 1] + hours[0]);
      return Math.max(1, minGap);
    }
  }

  // Minute step on "*" hour means sub-hourly
  if (hour === "*") {
    const minuteStep = /^\*\/(\d+)$/.exec(minute);
    if (minuteStep) return Math.max(1, parseInt(minuteStep[1], 10)) / 60;
    return 1;
  }

  return 24;
}

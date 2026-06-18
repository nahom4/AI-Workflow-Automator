import { auth } from "@/auth";
import { db, initDb } from "@/lib/db";
import { redirect } from "next/navigation";
import { UserRow } from "@/types/db";
import { getUserPlan, PLANS } from "@/lib/plans";
import Link from "next/link";
import UpgradePanel from "./UpgradePanel";

export const dynamic = "force-dynamic";

export default async function BillingPage({
  searchParams,
}: {
  searchParams: Promise<{ checkout?: string }>;
}) {
  const session = await auth();
  const userId = session?.user?.id;
  if (!userId) redirect("/login?callbackUrl=/account/billing");

  await initDb();
  const result = await db().execute({
    sql: "SELECT * FROM users WHERE id = ?",
    args: [userId],
  });
  const user = result.rows[0] as unknown as UserRow | undefined;
  if (!user) redirect("/login");

  const plan = await getUserPlan(userId);
  const isPro = plan.id === "pro";
  const sp = await searchParams;
  const justCheckedOut = sp.checkout === "success";

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-3xl font-bold tracking-tight">Billing</h1>
        <p className="text-gray-400 mt-1">Manage your plan and subscription.</p>
      </header>

      {justCheckedOut && (
        <div className="border border-green-500/30 bg-green-500/10 rounded-xl p-4 text-green-300 text-sm">
          Thanks! Your subscription is being activated. It can take a moment for Pro
          features to switch on while we receive confirmation from Paddle.
        </div>
      )}

      <section className="border border-gray-800 bg-gray-900/30 rounded-xl p-6">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <p className="text-sm text-gray-400 uppercase tracking-wider mb-1">
              Current plan
            </p>
            <h2 className="text-2xl font-bold text-white">{plan.name}</h2>
            {isPro && user.subscription_period_end ? (
              <p className="text-sm text-gray-400 mt-2">
                {user.subscription_status === "canceled"
                  ? `Access ends ${new Date(user.subscription_period_end).toLocaleDateString()}`
                  : `Renews ${new Date(user.subscription_period_end).toLocaleDateString()}`}
              </p>
            ) : !isPro ? (
              <p className="text-sm text-gray-400 mt-2">
                Free plan — {plan.maxAutomations} automations, daily runs, standard ranking.
              </p>
            ) : null}
          </div>

          <div className="flex items-center gap-3">
            {isPro ? (
              <>
                <a
                  href="mailto:support@example.com?subject=Cancel%20subscription"
                  className="text-sm text-gray-400 hover:text-gray-200 transition-colors px-4 py-2 border border-gray-700 hover:border-gray-500 rounded-lg"
                >
                  Cancel
                </a>
              </>
            ) : (
              <Link
                href="/pricing"
                className="text-sm bg-violet-600 hover:bg-violet-500 text-white font-medium px-4 py-2 rounded-lg transition-colors"
              >
                See Pro plan
              </Link>
            )}
          </div>
        </div>
      </section>

      {!isPro && (
        <section className="border border-violet-500/30 bg-gradient-to-br from-violet-900/20 to-gray-900/30 rounded-xl p-6">
          <h2 className="text-xl font-bold text-white mb-2">
            Upgrade to {PLANS.pro.name}
          </h2>
          <p className="text-sm text-gray-300 mb-5">
            Sharper AI ranking, {PLANS.pro.maxAutomations} automations, runs every{" "}
            {PLANS.pro.minScheduleHours} hours, Google Sheets + Gmail delivery.
          </p>
          <UpgradePanel />
        </section>
      )}

      <section className="border border-gray-800 bg-gray-900/30 rounded-xl p-6">
        <h2 className="text-lg font-semibold text-white mb-4">Your limits</h2>
        <dl className="grid sm:grid-cols-2 gap-4 text-sm">
          <Stat label="Automations" value={`Up to ${plan.maxAutomations}`} />
          <Stat label="Criteria per automation" value={`Up to ${plan.maxCriteriaPerAutomation}`} />
          <Stat label="Sources per automation" value={`Up to ${plan.maxSourcesPerAutomation}`} />
          <Stat
            label="Minimum run frequency"
            value={`Every ${plan.minScheduleHours} hour${plan.minScheduleHours === 1 ? "" : "s"}`}
          />
          <Stat label="AI ranking" value={plan.rankerTier === "advanced" ? "Advanced" : "Standard"} />
          <Stat label="Lead history" value={`${plan.leadHistoryDays} days`} />
          <Stat label="Google Sheets" value={plan.integrations.googleSheets ? "Yes" : "—"} />
          <Stat label="Gmail digest" value={plan.integrations.gmail ? "Yes" : "—"} />
        </dl>
      </section>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-gray-500 uppercase tracking-wider mb-1">{label}</dt>
      <dd className="text-gray-200 font-medium">{value}</dd>
    </div>
  );
}

import { db, initDb } from "@/lib/db";
import { AutomationRow } from "@/types/db";
import { auth } from "@/auth";
import { redirect } from "next/navigation";
import Link from "next/link";

export const dynamic = "force-dynamic";

const STATUS_STYLES: Record<string, string> = {
  active: "bg-green-900 text-green-300",
  paused: "bg-gray-800 text-gray-400",
  broken: "bg-red-900 text-red-300",
};

const VERTICAL_ICONS: Record<string, string> = {
  jobs: "💼",
  products: "📦",
  scholarships: "🎓",
  other: "⚡",
};

export default async function AutomationsPage() {
  const session = await auth();
  const userId = session?.user?.id;
  if (!userId) redirect("/login?callbackUrl=/automations");

  await initDb();
  const result = await db().execute({
    sql: "SELECT * FROM automations WHERE user_id = ? ORDER BY created_at DESC",
    args: [userId],
  });
  const automations = result.rows as unknown as AutomationRow[];

  if (automations.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center">
        <div className="text-6xl mb-6">⚡</div>
        <h1 className="text-2xl font-bold text-gray-100 mb-3">
          No automations yet
        </h1>
        <p className="text-gray-400 mb-8 max-w-sm">
          Describe what you want to track — jobs, products, scholarships — and
          get notified when new matches appear.
        </p>
        <Link
          href="/automations/new"
          className="bg-violet-600 hover:bg-violet-500 text-white font-medium px-6 py-3 rounded-lg transition-colors"
        >
          Create your first automation
        </Link>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-100">Automations</h1>
          <p className="text-gray-400 text-sm mt-1">
            {automations.length} automation{automations.length !== 1 ? "s" : ""}
          </p>
        </div>
        <Link
          href="/automations/new"
          className="bg-violet-600 hover:bg-violet-500 text-white font-medium px-4 py-2 rounded-lg transition-colors text-sm"
        >
          + New
        </Link>
      </div>

      <div className="space-y-3">
        {automations.map((a) => (
          <Link
            key={a.id}
            href={`/automations/${a.id}`}
            className="block bg-gray-900 border border-gray-800 rounded-xl p-5 hover:border-violet-700 transition-colors group"
          >
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0 flex items-start gap-3">
                <span className="text-2xl flex-shrink-0">
                  {VERTICAL_ICONS[a.vertical] ?? "⚡"}
                </span>
                <div className="min-w-0">
                  <h2 className="font-semibold text-gray-100 group-hover:text-violet-300 transition-colors truncate">
                    {a.name}
                  </h2>
                  <p className="text-gray-400 text-sm mt-0.5 truncate">
                    {a.intent_text}
                  </p>
                </div>
              </div>
              <span
                className={`text-xs font-semibold px-2 py-0.5 rounded flex-shrink-0 ${STATUS_STYLES[a.status] ?? "bg-gray-800 text-gray-400"}`}
              >
                {a.status}
              </span>
            </div>
            <div className="mt-3 flex items-center gap-4 text-xs text-gray-600">
              <span>{a.schedule_cron}</span>
              {a.last_run_at && (
                <span>
                  Last run:{" "}
                  {new Date(a.last_run_at).toLocaleDateString("en-US", {
                    month: "short",
                    day: "numeric",
                  })}
                </span>
              )}
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}

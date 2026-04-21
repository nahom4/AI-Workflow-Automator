import { db, initDb } from "@/lib/db";
import { AutomationRow } from "@/types/db";
import { WorkflowDefinition } from "@/types/workflow";
import Link from "next/link";

export const dynamic = "force-dynamic";

const ACTION_ICONS: Record<string, string> = {
  slack: "S",
  email: "E",
  http: "H",
};

const ACTION_COLORS: Record<string, string> = {
  slack: "bg-green-900 text-green-300",
  email: "bg-blue-900 text-blue-300",
  http: "bg-orange-900 text-orange-300",
};

export default async function AutomationsPage() {
  await initDb();
  const result = await db().execute(
    "SELECT * FROM automations ORDER BY created_at DESC"
  );
  const automations = result.rows as unknown as AutomationRow[];

  if (automations.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center">
        <div className="text-6xl mb-6">⚡</div>
        <h1 className="text-2xl font-bold text-gray-100 mb-3">
          No automations yet
        </h1>
        <p className="text-gray-400 mb-8 max-w-sm">
          Describe an automation in plain English and we&apos;ll generate a live
          webhook URL that runs it.
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
      </div>

      <div className="space-y-3">
        {automations.map((a) => {
          const workflow: WorkflowDefinition = JSON.parse(a.workflow);
          return (
            <Link
              key={a.id}
              href={`/automations/${a.id}`}
              className="block bg-gray-900 border border-gray-800 rounded-xl p-5 hover:border-violet-700 transition-colors group"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <h2 className="font-semibold text-gray-100 group-hover:text-violet-300 transition-colors truncate">
                    {a.name}
                  </h2>
                  <p className="text-gray-400 text-sm mt-1 truncate">
                    {a.description}
                  </p>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  {workflow.steps.map((step, i) => (
                    <span
                      key={i}
                      className={`text-xs font-bold px-2 py-0.5 rounded ${ACTION_COLORS[step.type] ?? "bg-gray-800 text-gray-400"}`}
                    >
                      {ACTION_ICONS[step.type] ?? step.type}
                    </span>
                  ))}
                </div>
              </div>
              <div className="mt-3 text-xs text-gray-600">
                Created{" "}
                {new Date(a.created_at).toLocaleDateString("en-US", {
                  month: "short",
                  day: "numeric",
                  year: "numeric",
                })}
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}

import { db, initDb } from "@/lib/db";
import { AutomationRow, LeadRow, RunRow } from "@/types/db";
import { notFound } from "next/navigation";
import Link from "next/link";

export const dynamic = "force-dynamic";

const STATUS_STYLES: Record<string, string> = {
  active: "bg-green-900 text-green-300",
  paused: "bg-gray-800 text-gray-400",
  broken: "bg-red-900 text-red-300",
};

const RUN_STATUS_STYLES: Record<string, string> = {
  success: "bg-green-900 text-green-300",
  error: "bg-red-900 text-red-300",
  running: "bg-yellow-900 text-yellow-300 animate-pulse",
};

export default async function AutomationDetailPage({
  params,
}: {
  params: { id: string };
}) {
  await initDb();

  const [autoResult, leadsResult, runsResult] = await Promise.all([
    db().execute({ sql: "SELECT * FROM automations WHERE id = ?", args: [params.id] }),
    db().execute({
      sql: "SELECT * FROM leads WHERE automation_id = ? ORDER BY score DESC LIMIT 10",
      args: [params.id],
    }),
    db().execute({
      sql: "SELECT * FROM runs WHERE automation_id = ? ORDER BY started_at DESC LIMIT 5",
      args: [params.id],
    }),
  ]);

  const automation = autoResult.rows[0] as unknown as AutomationRow | undefined;
  if (!automation) notFound();

  const leads = leadsResult.rows as unknown as LeadRow[];
  const runs = runsResult.rows as unknown as RunRow[];
  const spec = JSON.parse(automation.spec_json);

  return (
    <div className="max-w-2xl space-y-8">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <Link
            href="/automations"
            className="text-sm text-gray-500 hover:text-gray-300 transition-colors"
          >
            ← All automations
          </Link>
          <div className="flex items-center gap-3 mt-2">
            <h1 className="text-2xl font-bold text-gray-100">{automation.name}</h1>
            <span
              className={`text-xs font-semibold px-2 py-0.5 rounded ${STATUS_STYLES[automation.status] ?? "bg-gray-800 text-gray-400"}`}
            >
              {automation.status}
            </span>
          </div>
          <p className="text-gray-400 text-sm mt-1">{automation.intent_text}</p>
        </div>
      </div>

      {/* Spec details */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-3">
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">Vertical</p>
            <p className="text-gray-300">{automation.vertical}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">Schedule</p>
            <p className="text-gray-300 font-mono text-xs">{automation.schedule_cron}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">Sources</p>
            <p className="text-gray-300">{spec.sources?.join(", ")}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">Threshold</p>
            <p className="text-gray-300">{spec.threshold ?? 6} / 10</p>
          </div>
        </div>
        {spec.criteria?.length > 0 && (
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">Criteria</p>
            <div className="flex flex-wrap gap-1.5 mt-1">
              {spec.criteria.map((c: string) => (
                <span key={c} className="text-xs bg-gray-800 text-gray-300 px-2 py-0.5 rounded">
                  {c}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Recent leads */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <p className="text-xs text-gray-500 uppercase tracking-wider">
            Recent Leads ({leads.length})
          </p>
        </div>
        {leads.length === 0 ? (
          <p className="text-gray-600 text-sm">No leads yet — runs will populate this.</p>
        ) : (
          <div className="space-y-2">
            {leads.map((lead) => (
              <a
                key={lead.id}
                href={lead.url}
                target="_blank"
                rel="noopener noreferrer"
                className="block bg-gray-900 border border-gray-800 rounded-lg p-3 hover:border-violet-700 transition-colors"
              >
                <div className="flex items-start justify-between gap-3">
                  <p className="text-sm text-gray-200 font-medium">{lead.title}</p>
                  <span className="text-xs font-bold text-violet-400 flex-shrink-0">
                    {lead.score.toFixed(1)}
                  </span>
                </div>
                <p className="text-xs text-gray-500 mt-0.5">{lead.source_domain}</p>
              </a>
            ))}
          </div>
        )}
      </div>

      {/* Recent runs */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <p className="text-xs text-gray-500 uppercase tracking-wider">
            Recent Runs ({runs.length})
          </p>
          {runs.length > 0 && (
            <Link
              href={`/automations/${automation.id}/logs`}
              className="text-xs text-violet-400 hover:text-violet-300"
            >
              View all →
            </Link>
          )}
        </div>
        {runs.length === 0 ? (
          <p className="text-gray-600 text-sm">No runs yet — the worker will pick this up within 30 seconds.</p>
        ) : (
          <div className="space-y-2">
            {runs.map((run) => (
              <div
                key={run.id}
                className="bg-gray-900 border border-gray-800 rounded-lg p-3 flex items-center gap-3"
              >
                <span
                  className={`text-xs font-semibold px-2 py-0.5 rounded ${RUN_STATUS_STYLES[run.status] ?? "bg-gray-800 text-gray-400"}`}
                >
                  {run.status}
                </span>
                <span className="text-xs text-gray-500 font-mono">{run.id}</span>
                <span className="text-xs text-gray-600 ml-auto">
                  {new Date(run.started_at).toLocaleString()}
                </span>
                <span className="text-xs text-gray-500">
                  {run.items_kept}/{run.items_seen} kept
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

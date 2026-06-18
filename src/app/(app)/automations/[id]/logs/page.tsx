import { db, initDb } from "@/lib/db";
import { AutomationRow, RunRow } from "@/types/db";
import { notFound } from "next/navigation";
import Link from "next/link";

export const dynamic = "force-dynamic";

const STATUS_STYLES: Record<string, string> = {
  success: "bg-green-900 text-green-300",
  error: "bg-red-900 text-red-300",
  running: "bg-yellow-900 text-yellow-300 animate-pulse",
};

export default async function RunsPage({
  params,
}: {
  params: { id: string };
}) {
  await initDb();

  const automationResult = await db().execute({
    sql: "SELECT * FROM automations WHERE id = ?",
    args: [params.id],
  });
  const automation = automationResult.rows[0] as unknown as AutomationRow | undefined;
  if (!automation) notFound();

  const runsResult = await db().execute({
    sql: "SELECT * FROM runs WHERE automation_id = ? ORDER BY started_at DESC",
    args: [params.id],
  });
  const runs = runsResult.rows as unknown as RunRow[];

  return (
    <div className="max-w-2xl space-y-8">
      <div>
        <Link
          href={`/automations/${automation.id}`}
          className="text-sm text-gray-500 hover:text-gray-300 transition-colors"
        >
          ← {automation.name}
        </Link>
        <h1 className="text-2xl font-bold text-gray-100 mt-2">Run History</h1>
        <p className="text-gray-400 text-sm mt-1">
          {runs.length} run{runs.length !== 1 ? "s" : ""}
        </p>
      </div>

      {runs.length === 0 ? (
        <div className="text-center py-16">
          <p className="text-gray-500">No runs yet.</p>
          <p className="text-gray-600 text-sm mt-2">
            The worker polls every 30 seconds and will start a run soon.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {runs.map((run) => (
            <div
              key={run.id}
              className="bg-gray-900 border border-gray-800 rounded-xl p-4"
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-3">
                  <span
                    className={`text-xs font-semibold px-2 py-0.5 rounded ${STATUS_STYLES[run.status] ?? "bg-gray-800 text-gray-400"}`}
                  >
                    {run.status}
                  </span>
                  <code className="text-xs text-gray-500 font-mono">{run.id}</code>
                </div>
                <span className="text-xs text-gray-600">
                  {new Date(run.started_at).toLocaleString()}
                </span>
              </div>

              <div className="flex items-center gap-4 text-xs text-gray-500 mt-1">
                <span>{run.items_seen ?? 0} seen</span>
                <span>{run.items_kept ?? 0} kept</span>
                {run.finished_at && (
                  <span>
                    {Math.round((run.finished_at - run.started_at) / 1000)}s
                  </span>
                )}
              </div>

              {run.errors_json && (
                <details className="mt-2">
                  <summary className="text-xs text-red-400 cursor-pointer">
                    Errors
                  </summary>
                  <pre className="mt-2 text-xs text-red-300 font-mono bg-gray-950 rounded p-3 overflow-x-auto">
                    {JSON.stringify(JSON.parse(run.errors_json), null, 2)}
                  </pre>
                </details>
              )}

              <RunLogInline runId={run.id} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

async function RunLogInline({ runId }: { runId: string }) {
  const result = await db().execute({
    sql: "SELECT * FROM run_logs WHERE run_id = ? ORDER BY created_at ASC",
    args: [runId],
  });

  if (result.rows.length === 0) return null;

  return (
    <details className="mt-2">
      <summary className="text-xs text-gray-500 cursor-pointer hover:text-gray-300 transition-colors">
        Logs ({result.rows.length} lines)
      </summary>
      <div className="mt-2 bg-gray-950 rounded-lg p-3 font-mono text-xs space-y-1">
        {result.rows.map((row, i) => {
          const level = row.level as string;
          const color =
            level === "success"
              ? "text-green-400"
              : level === "error"
              ? "text-red-400"
              : level === "warning"
              ? "text-yellow-400"
              : "text-blue-400";
          return (
            <div key={i} className="flex gap-3">
              <span className="text-gray-600 select-none">
                {new Date(row.created_at as number).toLocaleTimeString()}
              </span>
              <span className={color}>{row.message as string}</span>
            </div>
          );
        })}
      </div>
    </details>
  );
}

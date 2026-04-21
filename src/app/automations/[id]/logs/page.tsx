import { db, initDb } from "@/lib/db";
import { AutomationRow, ExecutionRow } from "@/types/db";
import { notFound } from "next/navigation";
import Link from "next/link";
import LiveLogViewer from "./LiveLogViewer";

export const dynamic = "force-dynamic";

const STATUS_STYLES: Record<string, string> = {
  success: "bg-green-900 text-green-300",
  error: "bg-red-900 text-red-300",
  running: "bg-yellow-900 text-yellow-300 animate-pulse",
};

export default async function LogsPage({
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

  const executionsResult = await db().execute({
    sql: "SELECT * FROM executions WHERE automation_id = ? ORDER BY started_at DESC",
    args: [params.id],
  });
  const executions = executionsResult.rows as unknown as ExecutionRow[];

  const runningExecution = executions.find((e) => e.status === "running");

  return (
    <div className="max-w-2xl space-y-8">
      <div>
        <Link
          href={`/automations/${automation.id}`}
          className="text-sm text-gray-500 hover:text-gray-300 transition-colors"
        >
          ← {automation.name}
        </Link>
        <h1 className="text-2xl font-bold text-gray-100 mt-2">
          Execution History
        </h1>
        <p className="text-gray-400 text-sm mt-1">
          {executions.length} execution{executions.length !== 1 ? "s" : ""}
        </p>
      </div>

      {runningExecution && (
        <div className="bg-gray-900 border border-yellow-800 rounded-xl p-5">
          <div className="flex items-center gap-2 mb-3">
            <span className="w-2 h-2 bg-yellow-400 rounded-full animate-pulse" />
            <p className="text-yellow-300 font-medium text-sm">
              Live execution in progress
            </p>
          </div>
          <LiveLogViewer executionId={runningExecution.id} />
        </div>
      )}

      {executions.length === 0 ? (
        <div className="text-center py-16">
          <p className="text-gray-500">No executions yet.</p>
          <p className="text-gray-600 text-sm mt-2">
            Trigger the webhook to see execution logs here.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {executions.map((ex) => (
            <div
              key={ex.id}
              className="bg-gray-900 border border-gray-800 rounded-xl p-4"
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-3">
                  <span
                    className={`text-xs font-semibold px-2 py-0.5 rounded ${STATUS_STYLES[ex.status] ?? "bg-gray-800 text-gray-400"}`}
                  >
                    {ex.status}
                  </span>
                  <code className="text-xs text-gray-500 font-mono">{ex.id}</code>
                </div>
                <span className="text-xs text-gray-600">
                  {new Date(ex.started_at).toLocaleString()}
                </span>
              </div>
              {ex.error_message && (
                <p className="text-red-400 text-xs mt-2 font-mono">
                  {ex.error_message}
                </p>
              )}
              <details className="mt-2">
                <summary className="text-xs text-gray-500 cursor-pointer hover:text-gray-300 transition-colors">
                  Trigger payload
                </summary>
                <pre className="mt-2 text-xs text-gray-400 font-mono bg-gray-950 rounded p-3 overflow-x-auto">
                  {JSON.stringify(JSON.parse(ex.trigger_payload), null, 2)}
                </pre>
              </details>
              {ex.status !== "running" && (
                <ExecutionLogInline executionId={ex.id} />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

async function ExecutionLogInline({ executionId }: { executionId: string }) {
  const result = await db().execute({
    sql: "SELECT * FROM execution_logs WHERE execution_id = ? ORDER BY created_at ASC",
    args: [executionId],
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

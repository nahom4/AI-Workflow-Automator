import { db, initDb } from "@/lib/db";
import { AutomationRow } from "@/types/db";
import { WorkflowDefinition, WorkflowStep } from "@/types/workflow";
import { notFound } from "next/navigation";
import Link from "next/link";
import CopyButton from "./CopyButton";

export const dynamic = "force-dynamic";

const STEP_LABELS: Record<string, { label: string; color: string }> = {
  slack: { label: "Slack Message", color: "border-green-700 bg-green-950" },
  email: { label: "Send Email", color: "border-blue-700 bg-blue-950" },
  http: { label: "HTTP Request", color: "border-orange-700 bg-orange-950" },
};

function StepCard({ step, index }: { step: WorkflowStep; index: number }) {
  const meta = STEP_LABELS[step.type] ?? { label: step.type, color: "border-gray-700 bg-gray-900" };
  return (
    <div className={`border rounded-lg p-4 ${meta.color}`}>
      <div className="flex items-center gap-2 mb-3">
        <span className="text-xs text-gray-400 font-mono">Step {index + 1}</span>
        <span className="text-xs font-semibold text-gray-200 bg-gray-800 px-2 py-0.5 rounded">
          {meta.label}
        </span>
      </div>
      <div className="space-y-1.5">
        {Object.entries(step.params).map(([k, v]) => (
          <div key={k} className="flex gap-3 text-xs">
            <span className="text-gray-500 font-mono min-w-[120px] flex-shrink-0">{k}:</span>
            <span className="text-gray-300 font-mono break-all">
              {typeof v === "object" ? JSON.stringify(v) : String(v)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default async function AutomationDetailPage({
  params,
}: {
  params: { id: string };
}) {
  await initDb();
  const result = await db().execute({
    sql: "SELECT * FROM automations WHERE id = ?",
    args: [params.id],
  });

  const automation = result.rows[0] as unknown as AutomationRow | undefined;
  if (!automation) notFound();

  const workflow: WorkflowDefinition = JSON.parse(automation.workflow);
  const curlCommand = `curl -X POST ${automation.webhook_url} \\
  -H "Content-Type: application/json" \\
  -d '{"name":"Alice","email":"alice@example.com","message":"Hello!"}'`;

  return (
    <div className="max-w-2xl space-y-8">
      <div className="flex items-start justify-between gap-4">
        <div>
          <Link
            href="/automations"
            className="text-sm text-gray-500 hover:text-gray-300 transition-colors"
          >
            ← All automations
          </Link>
          <h1 className="text-2xl font-bold text-gray-100 mt-2">
            {automation.name}
          </h1>
          <p className="text-gray-400 text-sm mt-1">{automation.description}</p>
        </div>
        <Link
          href={`/automations/${automation.id}/logs`}
          className="flex-shrink-0 text-sm bg-gray-800 hover:bg-gray-700 text-gray-300 px-4 py-2 rounded-lg transition-colors"
        >
          View logs
        </Link>
      </div>

      <div>
        <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">
          Webhook URL
        </p>
        <div className="flex gap-2 items-stretch">
          <code className="flex-1 bg-gray-900 border border-gray-700 rounded-lg px-4 py-3 text-sm text-violet-300 font-mono break-all">
            {automation.webhook_url}
          </code>
          <CopyButton text={automation.webhook_url} />
        </div>
      </div>

      <div>
        <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">
          Test with curl
        </p>
        <pre className="bg-gray-900 border border-gray-800 rounded-xl p-4 text-sm text-gray-300 font-mono overflow-x-auto whitespace-pre-wrap">
          {curlCommand}
        </pre>
      </div>

      <div>
        <p className="text-xs text-gray-500 uppercase tracking-wider mb-3">
          Steps ({workflow.steps.length})
        </p>
        <div className="space-y-3">
          {workflow.steps.map((step, i) => (
            <StepCard key={i} step={step} index={i} />
          ))}
        </div>
      </div>

      <div className="border-t border-gray-800 pt-6 flex gap-3">
        <Link
          href={`/automations/${automation.id}/logs`}
          className="flex-1 bg-violet-600 hover:bg-violet-500 text-white font-medium py-3 rounded-xl transition-colors text-center text-sm"
        >
          View execution history
        </Link>
      </div>
    </div>
  );
}

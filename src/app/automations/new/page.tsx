"use client";

import { useState } from "react";
import { WorkflowDefinition, WorkflowStep } from "@/types/workflow";

type UIState = "input" | "preview" | "success";

const STEP_LABELS: Record<string, { label: string; color: string }> = {
  slack: { label: "Slack Message", color: "border-green-700 bg-green-950" },
  email: { label: "Send Email", color: "border-blue-700 bg-blue-950" },
  http: { label: "HTTP Request", color: "border-orange-700 bg-orange-950" },
};

function StepCard({ step, index }: { step: WorkflowStep; index: number }) {
  const meta = STEP_LABELS[step.type] ?? { label: step.type, color: "border-gray-700 bg-gray-900" };
  return (
    <div className={`border rounded-lg p-4 ${meta.color}`}>
      <div className="flex items-center gap-2 mb-2">
        <span className="text-xs text-gray-400 font-mono">Step {index + 1}</span>
        <span className="text-xs font-semibold text-gray-200 bg-gray-800 px-2 py-0.5 rounded">
          {meta.label}
        </span>
      </div>
      <div className="space-y-1">
        {Object.entries(step.params).map(([k, v]) => (
          <div key={k} className="flex gap-2 text-xs">
            <span className="text-gray-500 font-mono min-w-[100px]">{k}:</span>
            <span className="text-gray-300 font-mono break-all">
              {typeof v === "object" ? JSON.stringify(v) : String(v)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

const EXAMPLES = [
  "When someone submits my contact form, summarize their message with AI and post it to Slack",
  "Send a welcome email to new users who sign up",
  "POST form data to my webhook at https://example.com/hook when triggered",
];

export default function NewAutomationPage() {
  const [state, setState] = useState<UIState>("input");
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [workflow, setWorkflow] = useState<WorkflowDefinition | null>(null);
  const [webhookUrl, setWebhookUrl] = useState<string | null>(null);
  const [automationId, setAutomationId] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function handleParse() {
    if (!text.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/parse", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Parse failed");
      setWorkflow(data);
      setState("preview");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleCreate() {
    if (!workflow) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/automations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ description: text, workflow }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Create failed");
      setWebhookUrl(data.webhook_url);
      setAutomationId(data.id);
      setState("success");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function copyUrl() {
    if (!webhookUrl) return;
    await navigator.clipboard.writeText(webhookUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  const curlCommand = webhookUrl
    ? `curl -X POST ${webhookUrl} \\\n  -H "Content-Type: application/json" \\\n  -d '{"name":"Alice","email":"alice@example.com","message":"Hello!"}'`
    : "";

  return (
    <div className="max-w-2xl">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-100">New Automation</h1>
        <p className="text-gray-400 text-sm mt-1">
          Describe what you want to automate and we&apos;ll build it.
        </p>
      </div>

      {state === "input" && (
        <div className="space-y-4">
          <div>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleParse();
              }}
              placeholder="When someone submits my contact form, summarize their message with AI and post it to Slack..."
              rows={5}
              className="w-full bg-gray-900 border border-gray-700 rounded-xl p-4 text-gray-100 placeholder-gray-600 resize-none focus:outline-none focus:border-violet-600 transition-colors text-sm"
            />
            <p className="text-xs text-gray-600 mt-1">
              Tip: Ctrl+Enter to parse
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            {EXAMPLES.map((ex) => (
              <button
                key={ex}
                onClick={() => setText(ex)}
                className="text-xs bg-gray-800 hover:bg-gray-700 text-gray-400 px-3 py-1.5 rounded-lg transition-colors text-left"
              >
                {ex.length > 60 ? ex.slice(0, 60) + "…" : ex}
              </button>
            ))}
          </div>

          {error && (
            <p className="text-red-400 text-sm bg-red-950 border border-red-800 rounded-lg px-4 py-3">
              {error}
            </p>
          )}

          <button
            onClick={handleParse}
            disabled={loading || !text.trim()}
            className="w-full bg-violet-600 hover:bg-violet-500 disabled:bg-violet-900 disabled:text-violet-600 text-white font-medium py-3 rounded-xl transition-colors flex items-center justify-center gap-2"
          >
            {loading ? (
              <>
                <span className="animate-spin text-lg">⟳</span>
                Parsing with AI…
              </>
            ) : (
              "Parse with AI →"
            )}
          </button>
        </div>
      )}

      {state === "preview" && workflow && (
        <div className="space-y-6">
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
            <div className="flex items-center justify-between mb-4">
              <div>
                <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">
                  Automation name
                </p>
                <h2 className="font-semibold text-gray-100">{workflow.name}</h2>
              </div>
              <span className="text-xs bg-gray-800 text-gray-400 px-2 py-1 rounded">
                webhook trigger
              </span>
            </div>
            <p className="text-sm text-gray-400">{workflow.trigger.description}</p>
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

          {error && (
            <p className="text-red-400 text-sm bg-red-950 border border-red-800 rounded-lg px-4 py-3">
              {error}
            </p>
          )}

          <div className="flex gap-3">
            <button
              onClick={() => setState("input")}
              className="flex-1 bg-gray-800 hover:bg-gray-700 text-gray-300 font-medium py-3 rounded-xl transition-colors"
            >
              ← Edit
            </button>
            <button
              onClick={handleCreate}
              disabled={loading}
              className="flex-1 bg-violet-600 hover:bg-violet-500 disabled:bg-violet-900 disabled:text-violet-600 text-white font-medium py-3 rounded-xl transition-colors flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <span className="animate-spin">⟳</span> Creating…
                </>
              ) : (
                "Create Webhook →"
              )}
            </button>
          </div>
        </div>
      )}

      {state === "success" && webhookUrl && (
        <div className="space-y-6">
          <div className="bg-green-950 border border-green-800 rounded-xl p-5">
            <p className="text-green-400 font-semibold mb-1">
              Automation created!
            </p>
            <p className="text-green-300 text-sm">
              Your webhook is live and ready to receive requests.
            </p>
          </div>

          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">
              Webhook URL
            </p>
            <div className="flex gap-2">
              <code className="flex-1 bg-gray-900 border border-gray-700 rounded-lg px-4 py-3 text-sm text-violet-300 font-mono break-all">
                {webhookUrl}
              </code>
              <button
                onClick={copyUrl}
                className="bg-gray-800 hover:bg-gray-700 text-gray-300 px-4 py-3 rounded-lg transition-colors text-sm font-medium flex-shrink-0"
              >
                {copied ? "Copied!" : "Copy"}
              </button>
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

          <div className="flex gap-3">
            <a
              href="/automations/new"
              className="flex-1 bg-gray-800 hover:bg-gray-700 text-gray-300 font-medium py-3 rounded-xl transition-colors text-center"
            >
              Create another
            </a>
            <a
              href={`/automations/${automationId}`}
              className="flex-1 bg-violet-600 hover:bg-violet-500 text-white font-medium py-3 rounded-xl transition-colors text-center"
            >
              View automation →
            </a>
          </div>
        </div>
      )}
    </div>
  );
}

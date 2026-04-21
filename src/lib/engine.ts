import OpenAI from "openai";
import { db } from "@/lib/db";
import { dispatch } from "@/lib/executors";
import { sseChannel } from "@/lib/sse";
import { WorkflowDefinition, WorkflowStep } from "@/types/workflow";
import { nanoid } from "nanoid";

async function generateSummary(content: string): Promise<string> {
  const openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });
  const r = await openai.chat.completions.create({
    model: "gpt-4o-mini",
    messages: [
      {
        role: "system",
        content:
          "Summarize the following data in 2-3 sentences, extracting key information clearly.",
      },
      { role: "user", content },
    ],
    max_tokens: 150,
  });
  return r.choices[0].message.content ?? "No summary available.";
}

function resolveTokens(
  template: string,
  payload: Record<string, unknown>,
  aiSummary: string | null
): string {
  let result = template.replace(/\{\{trigger\.(\w+)\}\}/g, (_, key) => {
    const val = (payload as Record<string, unknown>)[key];
    return val !== undefined ? String(val) : `[missing:${key}]`;
  });

  if (aiSummary !== null) {
    result = result.replace(/\{\{ai\.summary\}\}/g, aiSummary);
  }

  return result;
}

function needsSummary(steps: WorkflowStep[]): boolean {
  return steps.some((s) => {
    const params = s.params as Record<string, unknown>;
    return Object.values(params).some(
      (v) => typeof v === "string" && v.includes("{{ai.summary}}")
    );
  });
}

function applyTemplates(
  step: WorkflowStep,
  payload: Record<string, unknown>,
  aiSummary: string | null
): WorkflowStep {
  const params = { ...step.params } as Record<string, string | undefined | Record<string, string>>;

  for (const key of Object.keys(params)) {
    const val = params[key];
    if (typeof val === "string") {
      params[key] = resolveTokens(val, payload, aiSummary);
    }
  }

  return { ...step, params } as WorkflowStep;
}

async function logLine(
  executionId: string,
  stepIndex: number,
  level: "info" | "success" | "error",
  message: string
) {
  const id = nanoid(10);
  const now = Date.now();
  await db().execute({
    sql: `INSERT INTO execution_logs (id, execution_id, step_index, level, message, created_at)
          VALUES (?, ?, ?, ?, ?, ?)`,
    args: [id, executionId, stepIndex, level, message, now],
  });
  sseChannel.push(executionId, { stepIndex, level, message, ts: now });
}

export async function runExecution(
  executionId: string,
  workflow: WorkflowDefinition,
  triggerPayload: Record<string, unknown>
) {
  await logLine(executionId, -1, "info", `Starting: ${workflow.name}`);

  let aiSummary: string | null = null;

  try {
    if (needsSummary(workflow.steps) && process.env.OPENAI_API_KEY) {
      await logLine(executionId, -1, "info", "Generating AI summary…");
      aiSummary = await generateSummary(JSON.stringify(triggerPayload));
      await logLine(executionId, -1, "info", "AI summary ready.");
    }

    for (let i = 0; i < workflow.steps.length; i++) {
      const step = workflow.steps[i];
      await logLine(executionId, i, "info", `Step ${i + 1}: running [${step.type}]`);

      const resolved = applyTemplates(step, triggerPayload, aiSummary);

      try {
        await dispatch(resolved);
        await logLine(
          executionId,
          i,
          "success",
          `Step ${i + 1}: [${step.type}] completed`
        );
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        await logLine(executionId, i, "error", `Step ${i + 1}: [${step.type}] failed — ${msg}`);
        throw err;
      }
    }

    await db().execute({
      sql: `UPDATE executions SET status='success', finished_at=? WHERE id=?`,
      args: [Date.now(), executionId],
    });
    await logLine(executionId, -1, "success", "All steps completed successfully.");
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    await db().execute({
      sql: `UPDATE executions SET status='error', finished_at=?, error_message=? WHERE id=?`,
      args: [Date.now(), msg, executionId],
    });
    await logLine(executionId, -1, "error", `Execution failed: ${msg}`);
  } finally {
    sseChannel.close(executionId);
    setTimeout(() => sseChannel.remove(executionId), 60_000);
  }
}

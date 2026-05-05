import { NextRequest, NextResponse } from "next/server";
import Groq from "groq-sdk";
import { z } from "zod";
import { nanoid } from "nanoid";
import { db } from "@/lib/db";

const chatRequestSchema = z.object({
  messages: z
    .array(
      z.object({
        role: z.enum(["user", "assistant"]),
        content: z.string(),
      })
    )
    .min(1),
  notify_email: z.string().email().optional(),
});

const TOOLS = [
  {
    type: "function",
    function: {
      name: "suggest_sources",
      description:
        "Suggest websites or APIs to monitor for the user's topic. Call this once you understand what the user wants to track.",
      parameters: {
        type: "object",
        properties: {
          vertical: {
            type: "string",
            enum: ["jobs", "products", "scholarships", "other"],
          },
          sources: {
            type: "array",
            items: { type: "string" },
            description: "Domain names to monitor, e.g. remoteok.com",
          },
          rationale: {
            type: "string",
            description: "Brief explanation of why these sources fit",
          },
        },
        required: ["vertical", "sources", "rationale"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "create_automation",
      description:
        "Create the automation. Only call this after the user has confirmed the sources and criteria.",
      parameters: {
        type: "object",
        properties: {
          name: { type: "string" },
          intent_text: { type: "string" },
          vertical: {
            type: "string",
            enum: ["jobs", "products", "scholarships", "other"],
          },
          sources: { type: "array", items: { type: "string" } },
          criteria: {
            type: "array",
            items: { type: "string" },
            description: "Keywords or requirements each result must match",
          },
          threshold: {
            type: "number",
            minimum: 1,
            maximum: 10,
            description: "Minimum AI relevance score (1–10) to keep a result",
          },
          schedule_cron: {
            type: "string",
            description: "Cron expression for how often to check, e.g. '0 */6 * * *'",
          },
        },
        required: [
          "name",
          "intent_text",
          "vertical",
          "sources",
          "criteria",
          "threshold",
          "schedule_cron",
        ],
      },
    },
  },
];

const SYSTEM = `You are an AI assistant that helps users set up automated monitoring workflows.

When a user describes what they want to track:
1. If their request is clear, use suggest_sources to propose relevant websites immediately.
2. If unclear, ask ONE concise clarifying question, then suggest sources.
3. After the user confirms sources and criteria, use create_automation.

Be specific. Keep responses under 3 sentences unless listing sources.`;

export async function POST(request: NextRequest) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const parsed = chatRequestSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.flatten() }, { status: 400 });
  }

  const { messages, notify_email } = parsed.data;

  const apiKey =
    process.env.GROQ_API_KEY ||
    process.env.GROQ_API_KEYS?.split(",")[0]?.trim();

  if (!apiKey) {
    return NextResponse.json(
      { error: "GROQ_API_KEY not configured" },
      { status: 503 }
    );
  }

  const groq = new Groq({ apiKey });

  try {
    const completion = await groq.chat.completions.create({
      model: process.env.GROQ_MODEL || "llama-3.3-70b-versatile",
      messages: [{ role: "system", content: SYSTEM }, ...messages],
      tools: TOOLS,
      tool_choice: "auto",
      max_tokens: 1024,
      temperature: 0.3,
    });

    const choice = completion.choices[0];
    const toolCalls = choice.message.tool_calls;

    if (toolCalls?.length) {
      const tc = toolCalls[0];
      let args: Record<string, unknown>;
      try {
        args = JSON.parse(tc.function.arguments) as Record<string, unknown>;
      } catch {
        return NextResponse.json({ error: "Malformed tool call" }, { status: 502 });
      }

      if (tc.function.name === "create_automation") {
        const database = db();
        const id = nanoid();
        const now = Date.now();
        const specJson = JSON.stringify({
          sources: args.sources,
          criteria: args.criteria,
          threshold: args.threshold,
        });
        await database.execute({
          sql: `INSERT INTO automations
                (id, name, intent_text, vertical, spec_json, schedule_cron,
                 notify_email, status, next_run_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)`,
          args: [
            id,
            args.name as string,
            args.intent_text as string,
            args.vertical as string,
            specJson,
            args.schedule_cron as string,
            notify_email ?? null,
            now,
            now,
            now,
          ],
        });

        return NextResponse.json({
          role: "assistant",
          content: `Done! Your automation "${args.name}" is active. I'll check ${(args.sources as string[]).join(", ")} on schedule.`,
          tool: "create_automation",
          automation_id: id,
        });
      }

      if (tc.function.name === "suggest_sources") {
        const textContent = choice.message.content;
        const fallback = `I suggest monitoring: ${(args.sources as string[]).join(", ")}. ${args.rationale}`;
        return NextResponse.json({
          role: "assistant",
          content: textContent ?? fallback,
          tool: "suggest_sources",
          sources: args.sources,
          vertical: args.vertical,
        });
      }
    }

    return NextResponse.json({
      role: "assistant",
      content: choice.message.content ?? "",
    });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: msg }, { status: 502 });
  }
}

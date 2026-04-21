import OpenAI from "openai";
import Groq from "groq-sdk";
import { WorkflowDefinition } from "@/types/workflow";
import { SYSTEM_PROMPT, FEW_SHOT_EXAMPLES } from "./prompts";

function getOpenAI() {
  return new OpenAI({ apiKey: process.env.OPENAI_API_KEY });
}

function getGroq() {
  return new Groq({ apiKey: process.env.GROQ_API_KEY });
}

async function parseWithOpenAI(text: string): Promise<WorkflowDefinition> {
  const openai = getOpenAI();
  const response = await openai.chat.completions.create({
    model: "gpt-4o",
    temperature: 0.2,
    response_format: { type: "json_object" },
    messages: [
      { role: "system", content: SYSTEM_PROMPT },
      ...FEW_SHOT_EXAMPLES,
      { role: "user", content: text },
    ],
  });
  const parsed = JSON.parse(response.choices[0].message.content!);
  if ("error" in parsed) throw new Error(String(parsed.error));
  return parsed as WorkflowDefinition;
}

async function parseWithGroq(text: string): Promise<WorkflowDefinition> {
  const groq = getGroq();
  const response = await groq.chat.completions.create({
    model: "llama-3.1-8b-instant",
    temperature: 0.2,
    response_format: { type: "json_object" },
    messages: [
      { role: "system", content: SYSTEM_PROMPT },
      FEW_SHOT_EXAMPLES[0],
      FEW_SHOT_EXAMPLES[1],
      { role: "user", content: text },
    ],
  });
  const parsed = JSON.parse(response.choices[0].message.content!);
  if ("error" in parsed) throw new Error(String(parsed.error));
  return parsed as WorkflowDefinition;
}

export async function parseWorkflow(
  naturalLanguageText: string
): Promise<WorkflowDefinition> {
  if (process.env.OPENAI_API_KEY) {
    try {
      return await parseWithOpenAI(naturalLanguageText);
    } catch (err) {
      console.warn("OpenAI parse failed, falling back to Groq:", err);
    }
  }

  return await parseWithGroq(naturalLanguageText);
}

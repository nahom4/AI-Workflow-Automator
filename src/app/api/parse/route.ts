import { NextRequest, NextResponse } from "next/server";
import { parseWorkflow } from "@/lib/ai/parser";

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => null);
  const text: string = body?.text?.trim();

  if (!text) {
    return NextResponse.json({ error: "text is required" }, { status: 400 });
  }

  try {
    const workflow = await parseWorkflow(text);
    return NextResponse.json(workflow);
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: msg }, { status: 422 });
  }
}

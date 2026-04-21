import { HttpAction } from "@/types/workflow";

export async function executeHttp(step: HttpAction): Promise<void> {
  const init: RequestInit = {
    method: step.params.method,
    headers: {
      "Content-Type": "application/json",
      ...step.params.headers,
    },
  };

  if (step.params.body_template && step.params.method !== "GET") {
    init.body = step.params.body_template;
  }

  const response = await fetch(step.params.url, init);

  if (!response.ok) {
    const body = await response.text().catch(() => "(no body)");
    throw new Error(`HTTP ${response.status} from ${step.params.url}: ${body}`);
  }
}

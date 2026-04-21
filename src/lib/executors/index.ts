import { WorkflowStep } from "@/types/workflow";
import { executeSlack } from "./slack";
import { executeEmail } from "./email";
import { executeHttp } from "./http";

export async function dispatch(step: WorkflowStep): Promise<void> {
  switch (step.type) {
    case "slack":
      return executeSlack(step);
    case "email":
      return executeEmail(step);
    case "http":
      return executeHttp(step);
    default:
      throw new Error(`Unknown action type: ${(step as { type: string }).type}`);
  }
}

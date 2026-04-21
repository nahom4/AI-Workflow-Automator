import { WorkflowDefinition } from "./workflow";

export interface ParseRequest {
  text: string;
}

export interface CreateAutomationRequest {
  description: string;
  workflow: WorkflowDefinition;
}

export interface TriggerWebhookResponse {
  executionId: string;
  logsUrl: string;
  message: string;
}

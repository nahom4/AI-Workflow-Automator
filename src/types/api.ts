import type { CreateAutomationInput, UpdateAutomationInput } from "@/lib/validation";

export type { CreateAutomationInput, UpdateAutomationInput };

export interface ApiError {
  error: string | object;
}

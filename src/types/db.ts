export interface AutomationRow {
  id: string;
  name: string;
  description: string;
  workflow: string;
  webhook_url: string;
  created_at: number;
  updated_at: number;
}

export interface ExecutionRow {
  id: string;
  automation_id: string;
  status: "running" | "success" | "error";
  trigger_payload: string;
  started_at: number;
  finished_at: number | null;
  error_message: string | null;
}

export interface ExecutionLogRow {
  id: string;
  execution_id: string;
  step_index: number;
  level: "info" | "success" | "error";
  message: string;
  created_at: number;
}

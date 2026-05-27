export interface UserRow {
  id: string;
  email: string;
  name: string | null;
  password_hash: string | null;
  created_at: number;
}

export interface AutomationRow {
  id: string;
  name: string;
  intent_text: string;
  vertical: "jobs" | "products" | "scholarships" | "other";
  spec_json: string; // JSON string — parse with JSON.parse()
  schedule_cron: string;
  notify_email: string | null;
  notify_whatsapp: string | null;
  status: "active" | "paused" | "broken";
  last_run_at: number | null;
  next_run_at: number;
  created_at: number;
  updated_at: number;
}

export interface LeadRow {
  id: string;
  automation_id: string;
  source_domain: string;
  external_id: string;
  url: string;
  title: string;
  raw_json: string; // JSON string
  score: number;
  matched_reasons: string | null;
  notified_at: number | null;
  created_at: number;
}

export interface SiteSpecRow {
  domain: string;
  vertical: string;
  tier: "api" | "pydantic" | "vision";
  spec_json: string; // JSON string
  user_confirmed: number; // 0 | 1
  last_validated_at: number | null;
  success_rate: number | null;
  created_at: number;
}

export interface RunRow {
  id: string;
  automation_id: string;
  status: "running" | "success" | "error";
  started_at: number;
  finished_at: number | null;
  items_seen: number;
  items_kept: number;
  errors_json: string | null;
}

export interface RunLogRow {
  id: string;
  run_id: string;
  level: "info" | "success" | "error" | "warning";
  message: string;
  created_at: number;
}

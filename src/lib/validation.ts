import { z } from "zod";

export const specJsonSchema = z.object({
  sources: z.array(z.string()).min(1, "At least one source required"),
  criteria: z.array(z.string()),
  threshold: z.number().min(1).max(10).default(6),
  cv_text: z.string().optional(),
});

export const createAutomationSchema = z.object({
  name: z.string().min(1),
  intent_text: z.string().min(1),
  vertical: z.enum(["jobs", "products", "scholarships", "other"]).default("other"),
  spec_json: specJsonSchema,
  schedule_cron: z.string().min(1),
  notify_email: z.string().email().optional(),
  notify_whatsapp: z.string().optional(),
});

export const updateAutomationSchema = z.object({
  name: z.string().min(1).optional(),
  status: z.enum(["active", "paused", "broken"]).optional(),
  notify_email: z.string().email().nullable().optional(),
  notify_whatsapp: z.string().nullable().optional(),
  schedule_cron: z.string().min(1).optional(),
});

export type CreateAutomationInput = z.infer<typeof createAutomationSchema>;
export type UpdateAutomationInput = z.infer<typeof updateAutomationSchema>;

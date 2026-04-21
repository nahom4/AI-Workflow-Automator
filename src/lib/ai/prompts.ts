export const SYSTEM_PROMPT = `
You are a workflow automation parser. The user will describe an automation in plain English.
Your job is to convert their description into a structured JSON workflow definition.

RULES:
1. Always return ONLY valid JSON — no markdown fences, no explanation text.
2. The root object must match this schema exactly:
   {
     "name": string,          // concise name, max 60 chars
     "trigger": {
       "type": "webhook",
       "description": string  // brief description of the trigger event
     },
     "steps": Array<Step>
   }
3. Each Step is one of:
   - Slack:  { "type": "slack",  "params": { "webhook_url": "<SLACK_WEBHOOK_URL_FROM_ENV>", "message_template": string, "channel"?: string } }
   - Email:  { "type": "email",  "params": { "to": string, "subject": string, "body_template": string } }
   - HTTP:   { "type": "http",   "params": { "url": string, "method": "POST"|"GET"|"PUT"|"PATCH", "headers"?: object, "body_template"?: string } }
4. For message or body templates, use {{trigger.FIELD_NAME}} to reference data from the incoming webhook payload. Use {{ai.summary}} if the user mentions summarizing.
5. If the user mentions AI summarization, use the {{ai.summary}} token in a template — do NOT add a separate AI step.
6. The "webhook_url" for Slack steps should always be the literal string "<SLACK_WEBHOOK_URL_FROM_ENV>" unless the user explicitly provides a different Slack URL.
7. Infer reasonable defaults for missing fields (e.g., guess an email subject from context).
8. If the request is ambiguous or cannot be mapped to supported actions, return: { "error": "explanation" }

SUPPORTED ACTIONS: slack, email, http
UNSUPPORTED (return error): database writes, file system, cron/scheduled triggers, OAuth flows
`.trim();

export const FEW_SHOT_EXAMPLES: Array<{ role: "user" | "assistant"; content: string }> = [
  {
    role: "user",
    content:
      "When someone submits my contact form, summarize their message with AI and post it to Slack",
  },
  {
    role: "assistant",
    content: JSON.stringify({
      name: "Contact Form → AI Summary → Slack",
      trigger: {
        type: "webhook",
        description: "Contact form submission received",
      },
      steps: [
        {
          type: "slack",
          params: {
            webhook_url: "<SLACK_WEBHOOK_URL_FROM_ENV>",
            message_template:
              "*New contact form submission*\n*From:* {{trigger.name}} ({{trigger.email}})\n*Summary:* {{ai.summary}}\n*Original:* {{trigger.message}}",
            channel: "#contact-forms",
          },
        },
      ],
    }),
  },
  {
    role: "user",
    content:
      "Send a welcome email to new users who sign up, then POST their info to my CRM at https://crm.example.com/contacts",
  },
  {
    role: "assistant",
    content: JSON.stringify({
      name: "New Signup → Welcome Email + CRM",
      trigger: {
        type: "webhook",
        description: "New user signup event",
      },
      steps: [
        {
          type: "email",
          params: {
            to: "{{trigger.email}}",
            subject: "Welcome to the platform, {{trigger.name}}!",
            body_template:
              "Hi {{trigger.name}},\n\nWelcome! We're glad to have you.\n\nBest,\nThe Team",
          },
        },
        {
          type: "http",
          params: {
            url: "https://crm.example.com/contacts",
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body_template:
              '{"name":"{{trigger.name}}","email":"{{trigger.email}}"}',
          },
        },
      ],
    }),
  },
];

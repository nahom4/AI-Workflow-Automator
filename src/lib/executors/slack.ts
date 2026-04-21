import { SlackAction } from "@/types/workflow";

export async function executeSlack(step: SlackAction): Promise<void> {
  const webhookUrl =
    step.params.webhook_url === "<SLACK_WEBHOOK_URL_FROM_ENV>"
      ? process.env.SLACK_WEBHOOK_URL
      : step.params.webhook_url;

  if (!webhookUrl) {
    throw new Error(
      "Slack webhook URL not configured. Set SLACK_WEBHOOK_URL in your environment."
    );
  }

  const response = await fetch(webhookUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: step.params.message_template }),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Slack responded ${response.status}: ${body}`);
  }
}

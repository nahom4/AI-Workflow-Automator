import { Resend } from "resend";
import { EmailAction } from "@/types/workflow";

let resend: Resend;

function getResend() {
  if (!resend) resend = new Resend(process.env.RESEND_API_KEY);
  return resend;
}

export async function executeEmail(step: EmailAction): Promise<void> {
  const { error } = await getResend().emails.send({
    from: process.env.RESEND_FROM_EMAIL ?? "onboarding@resend.dev",
    to: step.params.to,
    subject: step.params.subject,
    text: step.params.body_template,
  });

  if (error) {
    throw new Error(`Resend error: ${error.message}`);
  }
}

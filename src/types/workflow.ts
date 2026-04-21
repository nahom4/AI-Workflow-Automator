export type ActionType = "slack" | "email" | "http";

export interface SlackAction {
  type: "slack";
  params: {
    webhook_url: string;
    message_template: string;
    channel?: string;
  };
}

export interface EmailAction {
  type: "email";
  params: {
    to: string;
    subject: string;
    body_template: string;
  };
}

export interface HttpAction {
  type: "http";
  params: {
    url: string;
    method: "GET" | "POST" | "PUT" | "PATCH";
    headers?: Record<string, string>;
    body_template?: string;
  };
}

export type WorkflowStep = SlackAction | EmailAction | HttpAction;

export interface WorkflowDefinition {
  name: string;
  trigger: {
    type: "webhook";
    description: string;
  };
  steps: WorkflowStep[];
}

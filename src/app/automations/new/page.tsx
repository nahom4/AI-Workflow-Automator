"use client";

// Placeholder for Day 5 — will be replaced with the chat-first onboarding UI
// that uses Vercel AI SDK useChat() with tool calls.

import Link from "next/link";

export default function NewAutomationPage() {
  return (
    <div className="max-w-2xl">
      <div className="mb-8">
        <Link
          href="/automations"
          className="text-sm text-gray-500 hover:text-gray-300 transition-colors"
        >
          ← All automations
        </Link>
        <h1 className="text-2xl font-bold text-gray-100 mt-2">
          New Automation
        </h1>
        <p className="text-gray-400 text-sm mt-1">
          Chat UI coming in the next sprint.
        </p>
      </div>

      <div className="bg-gray-900 border border-gray-800 rounded-xl p-8 text-center text-gray-500">
        <div className="text-4xl mb-4">💬</div>
        <p className="font-medium text-gray-400">Chat-first creation UI</p>
        <p className="text-sm mt-2">
          Describe what you want to automate and the AI will suggest sources,
          criteria, and schedule.
        </p>
      </div>
    </div>
  );
}

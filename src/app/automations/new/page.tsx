"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

type Role = "user" | "assistant";

interface Message {
  role: Role;
  content: string;
  tool?: string;
  sources?: string[];
  automation_id?: string;
}

export default function NewAutomationPage() {
  const router = useRouter();
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content:
        "Hi! Tell me what you want to track — jobs, scholarships, products, news, anything. I'll find the right sources and set up automated monitoring for you.",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [notifyEmail, setNotifyEmail] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send() {
    const text = input.trim();
    if (!text || loading) return;

    const userMsg: Message = { role: "user", content: text };
    const next = [...messages, userMsg];
    setMessages(next);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: next
            .filter((m) => m.content)
            .map(({ role, content }) => ({ role, content })),
          notify_email: notifyEmail || undefined,
        }),
      });

      const data = (await res.json()) as Message & { error?: string };

      if (!res.ok) {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: `Error: ${data.error ?? "Something went wrong"}` },
        ]);
        return;
      }

      setMessages((prev) => [...prev, data]);

      if (data.automation_id) {
        setTimeout(() => router.push(`/automations/${data.automation_id}`), 2000);
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Connection error — please try again." },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  return (
    <div className="flex flex-col h-[calc(100vh-64px)] max-w-2xl mx-auto">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <Link
            href="/automations"
            className="text-sm text-gray-500 hover:text-gray-300 transition-colors"
          >
            ← All automations
          </Link>
          <h1 className="text-xl font-bold text-gray-100 mt-1">
            New Automation
          </h1>
        </div>
        <input
          type="email"
          placeholder="Notify email (optional)"
          value={notifyEmail}
          onChange={(e) => setNotifyEmail(e.target.value)}
          className="text-sm bg-gray-900 border border-gray-700 rounded-lg px-3 py-1.5 text-gray-300 placeholder-gray-600 focus:outline-none focus:border-gray-500"
        />
      </div>

      {/* Message list */}
      <div className="flex-1 overflow-y-auto space-y-3 pb-4">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                msg.role === "user"
                  ? "bg-blue-600 text-white rounded-br-sm"
                  : "bg-gray-800 text-gray-200 rounded-bl-sm"
              }`}
            >
              <p className="whitespace-pre-wrap">{msg.content}</p>

              {msg.tool === "suggest_sources" && msg.sources && (
                <div className="mt-2 pt-2 border-t border-gray-700">
                  <p className="text-xs text-gray-400 mb-1 font-medium">
                    Suggested sources:
                  </p>
                  <div className="flex flex-wrap gap-1">
                    {(msg.sources as string[]).map((s) => (
                      <span
                        key={s}
                        className="text-xs bg-gray-700 text-gray-300 px-2 py-0.5 rounded-full"
                      >
                        {s}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {msg.tool === "create_automation" && msg.automation_id && (
                <div className="mt-2 pt-2 border-t border-green-700">
                  <p className="text-xs text-green-400 font-medium">
                    Automation created — redirecting...
                  </p>
                </div>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-gray-800 rounded-2xl rounded-bl-sm px-4 py-3">
              <div className="flex gap-1">
                <span className="w-1.5 h-1.5 bg-gray-500 rounded-full animate-bounce [animation-delay:0ms]" />
                <span className="w-1.5 h-1.5 bg-gray-500 rounded-full animate-bounce [animation-delay:150ms]" />
                <span className="w-1.5 h-1.5 bg-gray-500 rounded-full animate-bounce [animation-delay:300ms]" />
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="border-t border-gray-800 pt-3 pb-2">
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Describe what you want to automate..."
            rows={2}
            className="flex-1 bg-gray-900 border border-gray-700 rounded-xl px-4 py-3 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-gray-500 resize-none"
          />
          <button
            onClick={send}
            disabled={loading || !input.trim()}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 text-white text-sm font-medium rounded-xl transition-colors self-end"
          >
            Send
          </button>
        </div>
        <p className="text-xs text-gray-600 mt-1.5">
          Press Enter to send · Shift+Enter for new line
        </p>
      </div>
    </div>
  );
}

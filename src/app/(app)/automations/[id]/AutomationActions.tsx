"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export default function AutomationActions({
  id,
  status,
}: {
  id: string;
  status: string;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function patch(updates: Record<string, unknown>) {
    setBusy(true);
    try {
      await fetch(`/api/automations/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updates),
      });
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!confirm("Delete this automation and all its leads? This cannot be undone.")) return;
    setBusy(true);
    try {
      await fetch(`/api/automations/${id}`, { method: "DELETE" });
      router.push("/automations");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center gap-2 flex-shrink-0">
      {status === "active" ? (
        <button
          onClick={() => patch({ status: "paused" })}
          disabled={busy}
          className="text-xs px-3 py-1.5 rounded-lg bg-gray-800 text-gray-300 hover:bg-gray-700 disabled:opacity-50 transition-colors"
        >
          Pause
        </button>
      ) : status === "paused" ? (
        <button
          onClick={() => patch({ status: "active" })}
          disabled={busy}
          className="text-xs px-3 py-1.5 rounded-lg bg-violet-700 text-white hover:bg-violet-600 disabled:opacity-50 transition-colors"
        >
          Resume
        </button>
      ) : null}
      <button
        onClick={remove}
        disabled={busy}
        className="text-xs px-3 py-1.5 rounded-lg bg-gray-900 border border-red-900 text-red-400 hover:bg-red-950 disabled:opacity-50 transition-colors"
      >
        Delete
      </button>
    </div>
  );
}

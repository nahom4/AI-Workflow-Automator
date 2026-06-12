"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { LeadRow } from "@/types/db";

type Props = {
  automationId: string;
  initial: LeadRow[];
  initialTotal: number;
};

type StreamState = "connecting" | "live" | "done" | "error";

const PREVIEW_COUNT = 3;

export default function LiveLeads({ automationId, initial, initialTotal }: Props) {
  const [leads, setLeads] = useState<LeadRow[]>(initial);
  const [total, setTotal] = useState(initialTotal);
  const [state, setState] = useState<StreamState>("connecting");
  const [open, setOpen] = useState(true);
  const seenIds = useRef(new Set(initial.map((l) => l.id)));

  useEffect(() => {
    const since = initial.reduce((m, l) => Math.max(m, l.created_at), 0);
    const url = `/api/automations/${automationId}/leads/stream${since ? `?since=${since}` : ""}`;
    const es = new EventSource(url);

    es.addEventListener("hello", () => setState("live"));

    es.addEventListener("lead", (ev) => {
      try {
        const lead = JSON.parse((ev as MessageEvent).data) as LeadRow;
        if (seenIds.current.has(lead.id)) return;
        seenIds.current.add(lead.id);
        setLeads((prev) => {
          const merged = [lead, ...prev];
          merged.sort((a, b) => b.score - a.score || b.created_at - a.created_at);
          return merged.slice(0, 10);
        });
        setTotal((t) => t + 1);
      } catch {
        /* ignore malformed event */
      }
    });

    es.addEventListener("done", () => {
      setState("done");
      es.close();
    });

    es.addEventListener("error", () => {
      if (es.readyState === EventSource.CLOSED) setState("error");
    });

    return () => es.close();
  }, [automationId, initial]);

  const indicator = {
    connecting: { dot: "bg-gray-500", label: "connecting" },
    live: { dot: "bg-green-500 animate-pulse", label: "live" },
    done: { dot: "bg-gray-600", label: "idle" },
    error: { dot: "bg-red-500", label: "disconnected" },
  }[state];

  const preview = leads.slice(0, PREVIEW_COUNT);
  const hiddenCount = leads.length - PREVIEW_COUNT;

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      {/* Header — always visible, acts as toggle */}
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-3 px-5 py-3.5 hover:bg-gray-800/50 transition-colors text-left"
      >
        <span className={`w-2 h-2 rounded-full flex-shrink-0 ${indicator.dot}`} />
        <p className="text-xs text-gray-400 uppercase tracking-wider flex-1">
          Top Leads
          <span className="text-gray-600 normal-case ml-1.5">
            {total} total · sneak peek · {indicator.label}
          </span>
        </p>
        {total > 0 && (
          <Link
            href={`/automations/${automationId}/leads`}
            onClick={(e) => e.stopPropagation()}
            className="text-xs text-violet-400 hover:text-violet-300 flex-shrink-0"
          >
            View all {total} →
          </Link>
        )}
        <span className="text-gray-600 text-xs ml-1 flex-shrink-0">
          {open ? "▲" : "▼"}
        </span>
      </button>

      {/* Collapsible body */}
      {open && (
        <div className="px-5 pb-4 space-y-2 border-t border-gray-800 pt-3">
          {leads.length === 0 ? (
            <p className="text-gray-600 text-sm">
              {state === "live"
                ? "Waiting for the worker to find leads…"
                : "No leads yet — runs will populate this."}
            </p>
          ) : (
            <>
              {preview.map((lead) => (
                <a
                  key={lead.id}
                  href={lead.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block bg-gray-800/60 border border-gray-700 rounded-lg p-3 hover:border-violet-700 transition-colors"
                >
                  <div className="flex items-start justify-between gap-3">
                    <p className="text-sm text-gray-200 font-medium leading-snug">{lead.title}</p>
                    <span className="text-xs font-bold text-violet-400 flex-shrink-0">
                      {lead.score.toFixed(1)}
                    </span>
                  </div>
                  <p className="text-xs text-gray-500 mt-0.5">{lead.source_domain}</p>
                </a>
              ))}

              {/* Fade-out teaser for hidden leads */}
              {hiddenCount > 0 && (
                <div className="relative">
                  <div className="absolute inset-0 bg-gradient-to-b from-transparent to-gray-900 pointer-events-none rounded-lg z-10" />
                  <div className="opacity-30 pointer-events-none">
                    <div className="bg-gray-800/60 border border-gray-700 rounded-lg p-3">
                      <div className="flex items-start justify-between gap-3">
                        <p className="text-sm text-gray-200 font-medium">{leads[PREVIEW_COUNT]?.title}</p>
                        <span className="text-xs font-bold text-violet-400">{leads[PREVIEW_COUNT]?.score.toFixed(1)}</span>
                      </div>
                    </div>
                  </div>
                  <Link
                    href={`/automations/${automationId}/leads`}
                    className="relative z-20 mt-2 flex items-center justify-center gap-1.5 text-xs text-violet-400 hover:text-violet-300 py-1"
                  >
                    + {hiddenCount} more lead{hiddenCount !== 1 ? "s" : ""} — view all →
                  </Link>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

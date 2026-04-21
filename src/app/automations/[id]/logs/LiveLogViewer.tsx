"use client";

import { useEffect, useRef, useState } from "react";

interface LogLine {
  stepIndex: number;
  level: "info" | "success" | "error";
  message: string;
  ts: number;
}

const LEVEL_COLOR = {
  info: "text-blue-400",
  success: "text-green-400",
  error: "text-red-400",
};

export default function LiveLogViewer({ executionId }: { executionId: string }) {
  const [logs, setLogs] = useState<LogLine[]>([]);
  const [done, setDone] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const es = new EventSource(`/api/logs/${executionId}`);

    es.onmessage = (e) => {
      const data = JSON.parse(e.data);
      if (data.type === "done") {
        setDone(true);
        es.close();
        return;
      }
      if ("message" in data) {
        setLogs((prev) => [...prev, data as LogLine]);
      }
    };

    es.onerror = () => {
      setDone(true);
      es.close();
    };

    return () => es.close();
  }, [executionId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  return (
    <div className="bg-gray-950 rounded-lg p-4 font-mono text-xs h-64 overflow-y-auto">
      {logs.length === 0 && !done && (
        <span className="text-gray-600">Waiting for logs…</span>
      )}
      {logs.map((log, i) => (
        <div key={i} className="flex gap-3 mb-0.5">
          <span className="text-gray-600 select-none flex-shrink-0">
            {new Date(log.ts).toLocaleTimeString()}
          </span>
          <span className={LEVEL_COLOR[log.level] ?? "text-gray-300"}>
            {log.message}
          </span>
        </div>
      ))}
      {!done && logs.length > 0 && (
        <div className="flex items-center gap-2 text-gray-600 mt-1">
          <span className="animate-pulse">●</span>
          <span>Running…</span>
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  );
}

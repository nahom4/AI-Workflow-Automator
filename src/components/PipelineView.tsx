"use client";

import { useState } from "react";

interface IntegrationConfig {
  automationId: string;
  googleSheetId: string | null;
  notifyGmail: boolean;
  hasGoogleToken: boolean;
  userEmail: string | null;
}

interface Props {
  sources: string[];
  threshold: number;
  vertical: string;
  totalLeads: number;
  integration: IntegrationConfig;
}

export default function PipelineView({ sources, threshold, vertical, totalLeads, integration }: Props) {
  const [sheetId, setSheetId] = useState(integration.googleSheetId ?? "");
  const [sheetUrl, setSheetUrl] = useState(
    integration.googleSheetId
      ? `https://docs.google.com/spreadsheets/d/${integration.googleSheetId}/edit`
      : null
  );
  const [gmailOn, setGmailOn] = useState(integration.notifyGmail);
  const [creatingSheet, setCreatingSheet] = useState(false);
  const [sheetError, setSheetError] = useState<string | null>(null);
  const [needsEnable, setNeedsEnable] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<string | null>(null);
  const [saving, setSaving] = useState<"gmail" | null>(null);
  const [saved, setSaved] = useState<"gmail" | null>(null);

  async function createSheet() {
    setCreatingSheet(true);
    setSheetError(null);
    setNeedsEnable(false);
    const res = await fetch(`/api/automations/${integration.automationId}/integrations/sheets`, {
      method: "POST",
    });
    setCreatingSheet(false);
    if (!res.ok) {
      const data = await res.json().catch(() => ({})) as { error?: string; enable_url?: string };
      if (data.error === "api_not_enabled" && data.enable_url) {
        window.open(data.enable_url, "_blank");
        setNeedsEnable(true);
        return;
      }
      setSheetError(data.error ?? "Failed to create spreadsheet");
      return;
    }
    const data = await res.json() as { sheet_id: string; sheet_url: string };
    setSheetId(data.sheet_id);
    setSheetUrl(data.sheet_url);
  }

  async function syncLeads() {
    setSyncing(true);
    setSyncResult(null);
    const res = await fetch(
      `/api/automations/${integration.automationId}/integrations/sheets/sync`,
      { method: "POST" }
    );
    setSyncing(false);
    const data = await res.json().catch(() => ({})) as { synced?: number; error?: string };
    setSyncResult(res.ok ? `Synced ${data.synced} lead(s) ✓` : (data.error ?? "Sync failed"));
  }

  async function disconnectSheet() {
    await fetch(`/api/automations/${integration.automationId}/integrations/sheets`, { method: "DELETE" });
    setSheetId("");
    setSheetUrl(null);
  }

  async function toggleGmail(val: boolean) {
    setGmailOn(val);
    setSaving("gmail");
    await fetch(`/api/automations/${integration.automationId}/integrations`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ notify_gmail: val }),
    });
    setSaving(null);
    setSaved("gmail");
    setTimeout(() => setSaved(null), 2000);
  }

  const sheetConfigured = sheetId.length > 0;

  return (
    <div className="space-y-4">
      <p className="text-xs text-gray-500 uppercase tracking-wider">Data Pipeline</p>

      {/* Flow diagram */}
      <div className="relative overflow-x-auto pb-2">
        <div className="flex items-stretch gap-0 min-w-max">

          {/* Sources */}
          <PipeNode
            icon="🌐"
            label="Sources"
            color="violet"
            badge={`${sources.length}`}
          >
            <ul className="space-y-0.5 mt-1">
              {sources.map((s) => (
                <li key={s} className="text-xs text-gray-400 truncate max-w-[120px]">{s}</li>
              ))}
            </ul>
          </PipeNode>

          <Arrow />

          {/* Scraper */}
          <PipeNode icon="🔍" label="Scraper" color="blue">
            <p className="text-xs text-gray-400 mt-1">Tier 1 · API</p>
            <p className="text-xs text-gray-400">Tier 2 · CSS</p>
            <p className="text-xs text-gray-500">Tier 3 · Vision</p>
          </PipeNode>

          <Arrow />

          {/* AI Ranker */}
          <PipeNode icon="🤖" label="AI Ranker" color="indigo">
            <p className="text-xs text-gray-400 mt-1">Groq LLM</p>
            <p className="text-xs text-gray-500 capitalize">{vertical}</p>
          </PipeNode>

          <Arrow />

          {/* Filter */}
          <PipeNode icon="⚡" label="Filter" color="amber">
            <p className="text-xs text-gray-400 mt-1">score ≥ {threshold}</p>
            <p className="text-xs text-gray-500">{totalLeads} kept</p>
          </PipeNode>

          <Arrow />

          {/* Outputs column */}
          <div className="flex flex-col gap-2">
            {/* Google Sheets */}
            <OutputNode
              icon="📊"
              label="Google Sheets"
              configured={sheetConfigured}
              active={sheetConfigured}
              noToken={!integration.hasGoogleToken}
            />
            {/* Gmail */}
            <OutputNode
              icon="📧"
              label="Gmail"
              configured={gmailOn}
              active={gmailOn}
              noToken={!integration.hasGoogleToken}
            />
          </div>
        </div>
      </div>

      {/* Integration config */}
      {!integration.hasGoogleToken ? (
        <div className="bg-gray-900 border border-gray-700 border-dashed rounded-xl p-4 text-sm text-gray-400">
          <span className="text-amber-400 font-medium">Connect Google</span> — sign out and sign back in with Google to enable Sheets and Gmail outputs.
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {/* Sheets config */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
            <div className="flex items-center gap-2">
              <span className="text-base">📊</span>
              <p className="text-sm font-medium text-gray-200">Google Sheets</p>
              {sheetConfigured && <span className="ml-auto text-xs bg-green-900 text-green-300 px-2 py-0.5 rounded">active</span>}
            </div>

            {sheetConfigured && sheetUrl ? (
              <div className="space-y-2">
                <a
                  href={sheetUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 text-xs text-violet-400 hover:text-violet-300 truncate"
                >
                  <span>↗</span>
                  <span className="truncate">Open spreadsheet</span>
                </a>
                <p className="text-xs text-gray-500">New leads are appended automatically on each run.</p>
                {syncResult && (
                  <p className={`text-xs ${syncResult.includes("✓") ? "text-green-400" : "text-red-400"}`}>
                    {syncResult}
                  </p>
                )}
                <button
                  onClick={syncLeads}
                  disabled={syncing}
                  className="w-full bg-violet-700 hover:bg-violet-600 disabled:opacity-50 text-white text-xs font-medium py-2 rounded-lg transition-colors"
                >
                  {syncing ? "Syncing…" : "Sync all leads now"}
                </button>
                <button
                  onClick={disconnectSheet}
                  className="w-full bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-gray-200 text-xs font-medium py-2 rounded-lg transition-colors"
                >
                  Disconnect
                </button>
              </div>
            ) : (
              <div className="space-y-2">
                {needsEnable ? (
                  <>
                    <p className="text-xs text-amber-400">
                      The Google Sheets API tab just opened. Enable it, then come back and click Retry.
                    </p>
                    <button
                      onClick={createSheet}
                      disabled={creatingSheet}
                      className="w-full bg-violet-700 hover:bg-violet-600 disabled:opacity-50 text-white text-xs font-medium py-2 rounded-lg transition-colors"
                    >
                      {creatingSheet ? "Creating…" : "Retry"}
                    </button>
                  </>
                ) : (
                  <>
                    <p className="text-xs text-gray-400">
                      Creates a new Google Spreadsheet in your Drive and appends a row for every new lead found.
                    </p>
                    {sheetError && <p className="text-xs text-red-400">{sheetError}</p>}
                    <button
                      onClick={createSheet}
                      disabled={creatingSheet}
                      className="w-full bg-violet-700 hover:bg-violet-600 disabled:opacity-50 text-white text-xs font-medium py-2 rounded-lg transition-colors"
                    >
                      {creatingSheet ? "Creating…" : "Create Spreadsheet"}
                    </button>
                  </>
                )}
              </div>
            )}
          </div>

          {/* Gmail config */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
            <div className="flex items-center gap-2">
              <span className="text-base">📧</span>
              <p className="text-sm font-medium text-gray-200">Gmail</p>
              {gmailOn && <span className="ml-auto text-xs bg-green-900 text-green-300 px-2 py-0.5 rounded">active</span>}
            </div>
            <p className="text-xs text-gray-400">
              Send a digest to <span className="text-gray-300">{integration.userEmail ?? "your Gmail"}</span> whenever new results are found.
            </p>
            <button
              onClick={() => toggleGmail(!gmailOn)}
              disabled={saving === "gmail"}
              className={`w-full text-xs font-medium py-2 rounded-lg transition-colors disabled:opacity-50 ${
                gmailOn
                  ? "bg-gray-700 hover:bg-gray-600 text-gray-200"
                  : "bg-violet-700 hover:bg-violet-600 text-white"
              }`}
            >
              {saving === "gmail" ? "Saving…" : saved === "gmail" ? "Saved ✓" : gmailOn ? "Disable Gmail" : "Enable Gmail"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function Arrow() {
  return (
    <div className="flex items-center px-1 self-center">
      <div className="w-6 h-px bg-gray-700" />
      <div className="w-0 h-0 border-t-4 border-b-4 border-l-6 border-t-transparent border-b-transparent border-l-gray-700" style={{ borderLeftWidth: 6 }} />
    </div>
  );
}

function PipeNode({
  icon,
  label,
  color,
  badge,
  children,
}: {
  icon: string;
  label: string;
  color: "violet" | "blue" | "indigo" | "amber";
  badge?: string;
  children?: React.ReactNode;
}) {
  const borders: Record<string, string> = {
    violet: "border-violet-800",
    blue: "border-blue-800",
    indigo: "border-indigo-800",
    amber: "border-amber-800",
  };
  const icons: Record<string, string> = {
    violet: "bg-violet-900/50",
    blue: "bg-blue-900/50",
    indigo: "bg-indigo-900/50",
    amber: "bg-amber-900/50",
  };
  return (
    <div className={`bg-gray-900 border ${borders[color]} rounded-xl p-3 min-w-[130px] flex flex-col`}>
      <div className="flex items-center gap-2">
        <span className={`text-lg leading-none p-1.5 rounded-lg ${icons[color]}`}>{icon}</span>
        <span className="text-xs font-semibold text-gray-200">{label}</span>
        {badge && (
          <span className="ml-auto text-xs bg-gray-800 text-gray-400 px-1.5 py-0.5 rounded">{badge}</span>
        )}
      </div>
      {children}
    </div>
  );
}

function OutputNode({
  icon,
  label,
  active,
  noToken,
}: {
  icon: string;
  label: string;
  configured?: boolean;
  active: boolean;
  noToken: boolean;
}) {
  return (
    <div
      className={`bg-gray-900 border rounded-xl p-3 min-w-[140px] flex items-center gap-2 ${
        noToken
          ? "border-gray-800 opacity-40"
          : active
          ? "border-green-700"
          : "border-gray-700 border-dashed"
      }`}
    >
      <span className="text-base">{icon}</span>
      <span className="text-xs font-medium text-gray-300">{label}</span>
      <span className={`ml-auto w-2 h-2 rounded-full flex-shrink-0 ${active ? "bg-green-400" : "bg-gray-700"}`} />
    </div>
  );
}

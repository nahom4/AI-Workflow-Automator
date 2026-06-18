"use client";

import { useState } from "react";

type Busy = "monthly" | "annual" | "crypto-monthly" | "crypto-annual" | null;

async function checkout(endpoint: string, cycle: "monthly" | "annual"): Promise<string> {
  const res = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cycle }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error((data as { error?: string }).error ?? `Checkout failed (${res.status})`);
  }
  const { url } = await res.json() as { url?: string };
  if (!url) throw new Error("No checkout URL returned");
  return url;
}

export default function UpgradeButton() {
  const [busy, setBusy] = useState<Busy>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleCard(cycle: "monthly" | "annual") {
    setBusy(cycle);
    setError(null);
    try {
      const url = await checkout("/api/billing/checkout", cycle);
      window.location.href = url;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
      setBusy(null);
    }
  }

  async function handleCrypto(cycle: "monthly" | "annual") {
    const key: Busy = cycle === "annual" ? "crypto-annual" : "crypto-monthly";
    setBusy(key);
    setError(null);
    try {
      const url = await checkout("/api/billing/crypto-checkout", cycle);
      window.location.href = url;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
      setBusy(null);
    }
  }

  return (
    <div className="space-y-3">
      <button
        onClick={() => handleCard("monthly")}
        disabled={busy !== null}
        className="block w-full text-center bg-violet-600 hover:bg-violet-500 disabled:bg-gray-700 disabled:cursor-not-allowed text-white font-medium px-5 py-3 rounded-lg transition-colors shadow-lg shadow-violet-600/30"
      >
        {busy === "monthly" ? "Loading checkout…" : "Upgrade — $29/month"}
      </button>
      <button
        onClick={() => handleCard("annual")}
        disabled={busy !== null}
        className="block w-full text-center border border-violet-500/40 hover:border-violet-400 text-violet-300 hover:text-violet-200 font-medium px-5 py-3 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {busy === "annual" ? "Loading checkout…" : "Annual — $23/mo (save 20%)"}
      </button>

      <div className="relative py-1">
        <div className="absolute inset-0 flex items-center">
          <div className="w-full border-t border-gray-700" />
        </div>
        <div className="relative flex justify-center">
          <span className="bg-gray-900 px-3 text-xs text-gray-500">or pay with crypto</span>
        </div>
      </div>

      <button
        onClick={() => handleCrypto("monthly")}
        disabled={busy !== null}
        className="block w-full text-center border border-orange-500/40 hover:border-orange-400 text-orange-300 hover:text-orange-200 font-medium px-5 py-3 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {busy === "crypto-monthly" ? "Loading checkout…" : "Crypto — $29/month"}
      </button>
      <button
        onClick={() => handleCrypto("annual")}
        disabled={busy !== null}
        className="block w-full text-center border border-orange-500/30 hover:border-orange-400/60 text-orange-400/70 hover:text-orange-300 font-medium px-5 py-3 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {busy === "crypto-annual" ? "Loading checkout…" : "Crypto annual — $23/mo (save 20%)"}
      </button>

      {error && (
        <p className="text-sm text-red-400 text-center pt-1">{error}</p>
      )}
    </div>
  );
}

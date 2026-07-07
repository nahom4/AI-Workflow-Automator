"use client";

import { useEffect, useState } from "react";

type Cycle = "monthly" | "annual";

interface X402Info {
  merchant: `0x${string}`;
  usdc: `0x${string}`;
  chainId: number;
  prices: { monthly: string; annual: string };
}

type Eip1193Provider = {
  request: (args: { method: string; params?: unknown[] | object }) => Promise<unknown>;
};

declare global {
  interface Window {
    ethereum?: Eip1193Provider;
  }
}

const BASE_CHAIN_PARAMS = {
  chainId: "0x2105",
  chainName: "Base",
  nativeCurrency: { name: "Ether", symbol: "ETH", decimals: 18 },
  rpcUrls: ["https://mainnet.base.org"],
  blockExplorerUrls: ["https://basescan.org"],
};

function randomNonce(): `0x${string}` {
  const buf = new Uint8Array(32);
  crypto.getRandomValues(buf);
  return ("0x" +
    Array.from(buf)
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("")) as `0x${string}`;
}

async function ensureBase(provider: Eip1193Provider): Promise<void> {
  const current = (await provider.request({ method: "eth_chainId" })) as string;
  if (current?.toLowerCase() === "0x2105") return;
  try {
    await provider.request({
      method: "wallet_switchEthereumChain",
      params: [{ chainId: "0x2105" }],
    });
  } catch (err) {
    const e = err as { code?: number };
    if (e?.code === 4902) {
      await provider.request({
        method: "wallet_addEthereumChain",
        params: [BASE_CHAIN_PARAMS],
      });
    } else {
      throw err;
    }
  }
}

export default function CryptoPayButton({
  cycle,
  label,
  variant = "primary",
  fullWidth = true,
}: {
  cycle: Cycle;
  label: string;
  variant?: "primary" | "secondary";
  fullWidth?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<X402Info | null>(null);
  const [infoError, setInfoError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/billing/x402-info")
      .then(async (r) => {
        const data = await r.json().catch(() => ({}));
        if (cancelled) return;
        if (!r.ok) {
          setInfoError((data as { error?: string }).error ?? `Failed to load (${r.status})`);
          return;
        }
        setInfo(data as X402Info);
      })
      .catch((e) => !cancelled && setInfoError(e instanceof Error ? e.message : "Network error"));
    return () => {
      cancelled = true;
    };
  }, []);

  async function handlePay() {
    if (!info) return;
    setBusy(true);
    setError(null);
    setStatus("Connecting wallet…");
    try {
      const provider = window.ethereum;
      if (!provider) throw new Error("No web3 wallet detected. Install MetaMask or Coinbase Wallet.");

      const accounts = (await provider.request({ method: "eth_requestAccounts" })) as string[];
      const from = accounts[0] as `0x${string}` | undefined;
      if (!from) throw new Error("No account selected");

      setStatus("Switching to Base…");
      await ensureBase(provider);

      const value = cycle === "annual" ? info.prices.annual : info.prices.monthly;
      const nowSec = Math.floor(Date.now() / 1000);
      const validAfter = "0";
      const validBefore = String(nowSec + 60 * 60); // 1h window
      const nonce = randomNonce();

      const typedData = {
        types: {
          EIP712Domain: [
            { name: "name", type: "string" },
            { name: "version", type: "string" },
            { name: "chainId", type: "uint256" },
            { name: "verifyingContract", type: "address" },
          ],
          TransferWithAuthorization: [
            { name: "from", type: "address" },
            { name: "to", type: "address" },
            { name: "value", type: "uint256" },
            { name: "validAfter", type: "uint256" },
            { name: "validBefore", type: "uint256" },
            { name: "nonce", type: "bytes32" },
          ],
        },
        domain: {
          name: "USD Coin",
          version: "2",
          chainId: info.chainId,
          verifyingContract: info.usdc,
        },
        primaryType: "TransferWithAuthorization",
        message: {
          from,
          to: info.merchant,
          value,
          validAfter,
          validBefore,
          nonce,
        },
      };

      setStatus("Sign in wallet to authorize $" + (cycle === "annual" ? 276 : 29) + " USDC…");
      const signature = (await provider.request({
        method: "eth_signTypedData_v4",
        params: [from, JSON.stringify(typedData)],
      })) as `0x${string}`;

      setStatus("Submitting payment on-chain…");
      const res = await fetch("/api/billing/x402-pay", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          cycle,
          authorization: {
            from,
            to: info.merchant,
            value,
            validAfter,
            validBefore,
            nonce,
            signature,
          },
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error((data as { error?: string }).error ?? `Server error (${res.status})`);
      }

      setStatus("Payment confirmed. Activating Pro…");
      window.location.href = "/account/billing?checkout=success&method=crypto";
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Payment failed";
      setError(msg);
      setStatus("");
      setBusy(false);
    }
  }

  const base = fullWidth ? "block w-full text-center" : "inline-block";
  const styles =
    variant === "primary"
      ? "bg-violet-600 hover:bg-violet-500 disabled:bg-gray-700 text-white shadow-lg shadow-violet-600/30"
      : "border border-violet-500/40 hover:border-violet-400 text-violet-300 hover:text-violet-200 disabled:opacity-50";

  return (
    <div className="space-y-2">
      <button
        onClick={handlePay}
        disabled={busy || !info}
        className={`${base} font-medium px-5 py-3 rounded-lg transition-colors disabled:cursor-not-allowed ${styles}`}
      >
        {busy ? status || "Working…" : label}
      </button>
      {infoError && <p className="text-xs text-red-400">Payment unavailable: {infoError}</p>}
      {error && <p className="text-xs text-red-400">{error}</p>}
      {!busy && !error && info && (
        <p className="text-xs text-gray-500">
          USDC on Base · gas covered by us · paid to{" "}
          <code className="text-gray-400">
            {info.merchant.slice(0, 6)}…{info.merchant.slice(-4)}
          </code>
        </p>
      )}
    </div>
  );
}

"use client";

import CryptoPayButton from "@/components/CryptoPayButton";

export default function UpgradePanel() {
  return (
    <div className="space-y-3">
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="flex-1">
          <CryptoPayButton cycle="monthly" label="Pay $29 USDC · Monthly" variant="primary" />
        </div>
        <div className="flex-1">
          <CryptoPayButton cycle="annual" label="Pay $276 USDC · Annual (save 20%)" variant="secondary" />
        </div>
      </div>

      <div className="relative py-2 max-w-md">
        <div className="absolute inset-0 flex items-center">
          <div className="w-full border-t border-gray-800" />
        </div>
        <div className="relative flex justify-center">
          <span className="bg-gray-900 px-3 text-xs text-gray-500">card payments</span>
        </div>
      </div>

      <button
        disabled
        className="inline-flex items-center gap-2 bg-gray-800/60 text-gray-500 font-medium px-5 py-2.5 rounded-lg cursor-not-allowed border border-gray-800 text-sm"
      >
        <span>Card · Coming soon</span>
      </button>
      <p className="text-xs text-gray-500">
        Card checkout is in verification with our processor. Use crypto for instant access today.
      </p>
    </div>
  );
}

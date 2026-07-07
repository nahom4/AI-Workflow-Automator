"use client";

import CryptoPayButton from "@/components/CryptoPayButton";

export default function UpgradeButton() {
  return (
    <div className="space-y-3">
      <CryptoPayButton cycle="monthly" label="Pay with USDC — $29/month" variant="primary" />
      <CryptoPayButton cycle="annual" label="Annual — $276 ($23/mo, save 20%)" variant="secondary" />

      <div className="relative py-2">
        <div className="absolute inset-0 flex items-center">
          <div className="w-full border-t border-gray-800" />
        </div>
        <div className="relative flex justify-center">
          <span className="bg-gray-900 px-3 text-xs text-gray-500">card payments</span>
        </div>
      </div>

      <button
        disabled
        className="block w-full text-center bg-gray-800/60 text-gray-500 font-medium px-5 py-3 rounded-lg cursor-not-allowed border border-gray-800"
      >
        Card · Coming soon
      </button>
      <p className="text-xs text-gray-500 text-center">
        Card checkout is in verification with our processor. Use crypto for instant access today.
      </p>
    </div>
  );
}

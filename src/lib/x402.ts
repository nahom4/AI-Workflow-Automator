/**
 * EIP-3009 USDC transferWithAuthorization relayer.
 *
 * Flow:
 *   1. Client constructs an EIP-712 TransferWithAuthorization message addressed
 *      to the merchant wallet for the price of the chosen cycle, and the user
 *      signs it via their wallet (no gas, just a signature).
 *   2. Server validates the typed data (`to`, `value`, expiry) matches what we
 *      expect for the plan, then submits the authorization on-chain using the
 *      RELAYER private key. The relayer pays gas (~$0.0001 on Base).
 *   3. USDC's contract enforces uniqueness of (`from`, `nonce`) so replay is
 *      handled at the protocol layer.
 *
 * Env vars:
 *   MERCHANT_USDC_ADDRESS   — receives USDC payment (your Base wallet address)
 *   RELAYER_PRIVATE_KEY     — hex-prefixed private key of the gas-paying wallet
 *   BASE_RPC_URL            — optional, defaults to https://mainnet.base.org
 */

import { createPublicClient, createWalletClient, http, parseAbi, type Hex } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { base } from "viem/chains";

// USDC native on Base mainnet (6 decimals).
export const USDC_BASE_ADDRESS = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913" as const;
const USDC_DECIMALS = 6;

// Prices in 6-decimal USDC base units (USDC has 6 decimals on Base).
const PRICE_BY_CYCLE = {
  monthly: BigInt("29000000"),    // 29 USDC
  annual: BigInt("276000000"),    // 276 USDC = $23/mo × 12
} as const;

const PERIOD_MS_BY_CYCLE = {
  monthly: 30 * 24 * 60 * 60 * 1000,
  annual: 365 * 24 * 60 * 60 * 1000,
} as const;

const USDC_ABI = parseAbi([
  "function transferWithAuthorization(address from, address to, uint256 value, uint256 validAfter, uint256 validBefore, bytes32 nonce, uint8 v, bytes32 r, bytes32 s)",
]);

export type Cycle = "monthly" | "annual";

export interface SignedAuthorization {
  from: Hex;
  to: Hex;
  value: string;            // decimal string of USDC base units
  validAfter: string;       // decimal string of unix seconds
  validBefore: string;      // decimal string of unix seconds
  nonce: Hex;               // 32-byte hex
  signature: Hex;           // 65-byte hex (r || s || v)
}

export interface RelayResult {
  txHash: Hex;
  periodEndMs: number;
}

export function getMerchantAddress(): Hex {
  const addr = process.env.MERCHANT_USDC_ADDRESS;
  if (!addr || !/^0x[a-fA-F0-9]{40}$/.test(addr)) {
    throw new Error("MERCHANT_USDC_ADDRESS is not configured (expected 0x-prefixed 40-hex-char address)");
  }
  return addr as Hex;
}

function getRelayerKey(): Hex {
  const k = process.env.RELAYER_PRIVATE_KEY;
  if (!k || !/^0x[a-fA-F0-9]{64}$/.test(k)) {
    throw new Error("RELAYER_PRIVATE_KEY is not configured (expected 0x-prefixed 64-hex-char private key)");
  }
  return k as Hex;
}

function getRpcUrl(): string {
  return process.env.BASE_RPC_URL ?? "https://mainnet.base.org";
}

export function expectedValueForCycle(cycle: Cycle): bigint {
  return PRICE_BY_CYCLE[cycle];
}

export function periodEndForCycle(cycle: Cycle, fromMs = Date.now()): number {
  return fromMs + PERIOD_MS_BY_CYCLE[cycle];
}

/**
 * The EIP-712 domain + types the client must sign. We export it so the frontend
 * builds the exact same struct — any mismatch and USDC will reject the signature.
 */
export const USDC_EIP712_DOMAIN = {
  name: "USD Coin",
  version: "2",
  chainId: base.id,
  verifyingContract: USDC_BASE_ADDRESS,
} as const;

export const TRANSFER_AUTH_TYPES = {
  TransferWithAuthorization: [
    { name: "from", type: "address" },
    { name: "to", type: "address" },
    { name: "value", type: "uint256" },
    { name: "validAfter", type: "uint256" },
    { name: "validBefore", type: "uint256" },
    { name: "nonce", type: "bytes32" },
  ],
} as const;

/**
 * Split a 65-byte 0x-prefixed signature into (v, r, s) for the contract call.
 */
function splitSig(sig: Hex): { v: number; r: Hex; s: Hex } {
  if (!/^0x[a-fA-F0-9]{130}$/.test(sig)) {
    throw new Error("Invalid signature length — expected 65 bytes (130 hex chars)");
  }
  const r = ("0x" + sig.slice(2, 66)) as Hex;
  const s = ("0x" + sig.slice(66, 130)) as Hex;
  let v = parseInt(sig.slice(130, 132), 16);
  // EIP-155 / legacy adjustment — USDC expects v in {27, 28}.
  if (v < 27) v += 27;
  return { v, r, s };
}

/**
 * Validate that the user-signed authorization is what we expect for `cycle`,
 * then submit it to the USDC contract on Base using the relayer wallet.
 * Throws if validation fails or the transaction reverts.
 */
export async function relayAuthorization(
  auth: SignedAuthorization,
  cycle: Cycle,
): Promise<RelayResult> {
  const merchant = getMerchantAddress();
  const expectedValue = expectedValueForCycle(cycle);
  const value = BigInt(auth.value);
  const validBefore = BigInt(auth.validBefore);
  const nowSec = BigInt(Math.floor(Date.now() / 1000));

  if (auth.to.toLowerCase() !== merchant.toLowerCase()) {
    throw new Error(`Recipient mismatch: expected ${merchant}, got ${auth.to}`);
  }
  if (value !== expectedValue) {
    throw new Error(`Value mismatch for ${cycle}: expected ${expectedValue}, got ${value}`);
  }
  if (validBefore <= nowSec) {
    throw new Error("Authorization has expired");
  }
  if (!/^0x[a-fA-F0-9]{64}$/.test(auth.nonce)) {
    throw new Error("Invalid nonce — expected 32-byte hex");
  }

  const account = privateKeyToAccount(getRelayerKey());
  const rpc = getRpcUrl();
  const publicClient = createPublicClient({ chain: base, transport: http(rpc) });
  const walletClient = createWalletClient({ account, chain: base, transport: http(rpc) });

  const { v, r, s } = splitSig(auth.signature);

  const txHash = await walletClient.writeContract({
    address: USDC_BASE_ADDRESS,
    abi: USDC_ABI,
    functionName: "transferWithAuthorization",
    args: [
      auth.from,
      auth.to,
      value,
      BigInt(auth.validAfter),
      validBefore,
      auth.nonce,
      v,
      r,
      s,
    ],
  });

  const receipt = await publicClient.waitForTransactionReceipt({ hash: txHash, timeout: 60_000 });
  if (receipt.status !== "success") {
    throw new Error(`USDC transferWithAuthorization reverted (tx: ${txHash})`);
  }

  return { txHash, periodEndMs: periodEndForCycle(cycle) };
}

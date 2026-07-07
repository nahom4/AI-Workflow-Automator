import { NextResponse } from "next/server";
import { getMerchantAddress, expectedValueForCycle, USDC_BASE_ADDRESS } from "@/lib/x402";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    return NextResponse.json({
      merchant: getMerchantAddress(),
      usdc: USDC_BASE_ADDRESS,
      chainId: 8453,
      prices: {
        monthly: expectedValueForCycle("monthly").toString(),
        annual: expectedValueForCycle("annual").toString(),
      },
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Misconfigured";
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}

import { auth } from "@/auth";
import MarketingNav from "@/components/MarketingNav";
import Link from "next/link";
import { PLANS } from "@/lib/plans";
import UpgradeButton from "./UpgradeButton";

export const metadata = {
  title: "Pricing — AI Workflow Automator",
  description:
    "One simple plan. Free to start. $29/month for sharper AI ranking, faster runs, and more automations.",
};

export default async function PricingPage() {
  const session = await auth();
  const isSignedIn = !!session?.user;

  const free = PLANS.free;
  const pro = PLANS.pro;

  const proCtaHref = !isSignedIn ? "/signup?next=/pricing" : null;

  return (
    <>
      <MarketingNav />

      <div className="relative overflow-hidden">
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[600px] h-[600px] bg-violet-600/10 rounded-full blur-3xl pointer-events-none" />

        <section className="relative max-w-5xl mx-auto px-6 pt-20 pb-12 text-center">
          <h1 className="text-4xl sm:text-5xl md:text-6xl font-bold tracking-tight text-white">
            Simple pricing.
            <br />
            <span className="bg-gradient-to-r from-violet-400 to-fuchsia-400 bg-clip-text text-transparent">
              Built to grow with you.
            </span>
          </h1>
          <p className="mt-6 max-w-xl mx-auto text-lg text-gray-400">
            Start free. Upgrade when you want sharper AI and more capacity. Cancel anytime.
          </p>
        </section>
      </div>

      <section className="max-w-5xl mx-auto px-6 pb-20">
        <div className="grid md:grid-cols-2 gap-6">
          <div className="border border-gray-800 bg-gray-900/30 rounded-2xl p-8 flex flex-col">
            <div>
              <h2 className="text-2xl font-bold text-white">{free.name}</h2>
              <p className="text-sm text-gray-400 mt-1">Try the full workflow with limits.</p>
              <div className="mt-6 mb-8">
                <span className="text-5xl font-bold text-white">$0</span>
                <span className="text-gray-400 ml-2">forever</span>
              </div>
              <ul className="space-y-3 text-sm text-gray-300">
                <Feature>{free.maxAutomations} active automations</Feature>
                <Feature>Up to {free.maxCriteriaPerAutomation} criteria per automation</Feature>
                <Feature>Up to {free.maxSourcesPerAutomation} sources per automation</Feature>
                <Feature>Runs once per day</Feature>
                <Feature>Standard AI ranking model</Feature>
                <Feature>Email notifications</Feature>
                <Feature>{free.leadHistoryDays}-day lead history</Feature>
              </ul>
            </div>
            <div className="mt-8 pt-6 border-t border-gray-800">
              <Link
                href={isSignedIn ? "/automations" : "/signup"}
                className="block w-full text-center bg-gray-800 hover:bg-gray-700 text-white font-medium px-5 py-3 rounded-lg transition-colors"
              >
                {isSignedIn ? "Go to dashboard" : "Start free"}
              </Link>
            </div>
          </div>

          <div className="relative border border-violet-500/40 bg-gradient-to-br from-violet-900/20 to-gray-900/30 rounded-2xl p-8 flex flex-col shadow-xl shadow-violet-900/20">
            <div className="absolute -top-3 right-6 px-3 py-1 rounded-full bg-violet-600 text-white text-xs font-semibold">
              Most popular
            </div>
            <div>
              <h2 className="text-2xl font-bold text-white">{pro.name}</h2>
              <p className="text-sm text-gray-400 mt-1">
                For serious tracking with sharper AI.
              </p>
              <div className="mt-6 mb-2">
                <span className="text-5xl font-bold text-white">${pro.priceMonthly}</span>
                <span className="text-gray-400 ml-2">/month</span>
              </div>
              <p className="text-sm text-violet-300 mb-6">
                Or ${pro.priceAnnualMonthly}/mo billed annually — save 20%
              </p>
              <ul className="space-y-3 text-sm text-gray-200">
                <Feature highlight>Sharper AI ranking model — catches nuance, fewer false positives</Feature>
                <Feature highlight>Resume / profile-aware scoring</Feature>
                <Feature>{pro.maxAutomations} active automations</Feature>
                <Feature>Up to {pro.maxCriteriaPerAutomation} criteria per automation</Feature>
                <Feature>Up to {pro.maxSourcesPerAutomation} sources per automation</Feature>
                <Feature>Runs as often as every {pro.minScheduleHours} hours</Feature>
                <Feature>Google Sheets sync</Feature>
                <Feature>Gmail digest delivery</Feature>
                <Feature>{pro.leadHistoryDays}-day lead history</Feature>
                <Feature>Priority email support</Feature>
              </ul>
            </div>
            <div className="mt-8 pt-6 border-t border-violet-500/20">
              {proCtaHref ? (
                <Link
                  href={proCtaHref}
                  className="block w-full text-center bg-violet-600 hover:bg-violet-500 text-white font-medium px-5 py-3 rounded-lg transition-colors shadow-lg shadow-violet-600/30"
                >
                  Create account to upgrade
                </Link>
              ) : (
                <UpgradeButton />
              )}
            </div>
          </div>
        </div>

        <div className="mt-16 max-w-3xl mx-auto">
          <h2 className="text-2xl font-bold text-white text-center mb-8">
            Frequently asked
          </h2>
          <div className="space-y-4">
            <Faq q="Can I cancel anytime?">
              Yes. Cancel from your account page and you keep Pro until the end of the
              billing period. After that, you drop back to the Free plan automatically —
              your automations and leads stay; only the limits change.
            </Faq>
            <Faq q="What does &quot;sharper AI ranking&quot; actually mean?">
              The Free plan uses a fast, capable model for scoring results 1–10 against
              your criteria. Pro upgrades to a more advanced reasoning model that picks
              up subtler matches, handles complex criteria better, and produces crisper
              cataloging — fewer good leads filtered out, fewer junk leads slipping through.
            </Faq>
            <Faq q="What payment methods do you accept?">
              All major credit and debit cards via Paddle. We also accept crypto —
              Bitcoin, Ethereum, USDC, and more — through Coinbase Commerce. Choose your
              preferred method at checkout.
            </Faq>
            <Faq q="Can I switch between monthly and annual later?">
              Yes. Switch from your account page. Annual gives you a 20% discount and is
              billed upfront once a year.
            </Faq>
            <Faq q="What happens if a run fails?">
              We retry automatically and log every error visible in your run history.
              You&apos;re never charged extra for retries.
            </Faq>
          </div>
        </div>
      </section>

      <footer className="border-t border-gray-800/60 py-10 mt-10">
        <div className="max-w-5xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-4 text-sm text-gray-500">
          <p>© {new Date().getFullYear()} AI Workflow Automator</p>
          <div className="flex items-center gap-6">
            <Link href="/" className="hover:text-gray-300 transition-colors">
              Home
            </Link>
            <Link href="/terms" className="hover:text-gray-300 transition-colors">
              Terms
            </Link>
            <Link href="/privacy" className="hover:text-gray-300 transition-colors">
              Privacy
            </Link>
            <Link href="/refund" className="hover:text-gray-300 transition-colors">
              Refunds
            </Link>
            <Link href="/login" className="hover:text-gray-300 transition-colors">
              Sign in
            </Link>
          </div>
        </div>
      </footer>
    </>
  );
}

function Feature({
  children,
  highlight = false,
}: {
  children: React.ReactNode;
  highlight?: boolean;
}) {
  return (
    <li className="flex items-start gap-3">
      <svg
        className={`w-5 h-5 mt-0.5 shrink-0 ${highlight ? "text-violet-400" : "text-green-500"}`}
        viewBox="0 0 20 20"
        fill="currentColor"
      >
        <path
          fillRule="evenodd"
          d="M16.704 5.29a1 1 0 010 1.42l-8 8a1 1 0 01-1.42 0l-4-4a1 1 0 011.42-1.42L8 12.58l7.29-7.29a1 1 0 011.414 0z"
          clipRule="evenodd"
        />
      </svg>
      <span>{children}</span>
    </li>
  );
}

function Faq({ q, children }: { q: string; children: React.ReactNode }) {
  return (
    <details className="border border-gray-800 bg-gray-900/30 rounded-xl group">
      <summary className="cursor-pointer list-none p-5 flex items-center justify-between font-medium text-white">
        <span>{q}</span>
        <svg
          className="w-5 h-5 text-gray-500 transition-transform group-open:rotate-180"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </summary>
      <div className="px-5 pb-5 text-sm text-gray-400 leading-relaxed">{children}</div>
    </details>
  );
}

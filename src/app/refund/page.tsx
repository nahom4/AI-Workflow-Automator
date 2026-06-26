import Link from "next/link";
import MarketingNav from "@/components/MarketingNav";

export const metadata = {
  title: "Refund Policy — AI Workflow Automator",
};

export default function RefundPage() {
  return (
    <>
      <MarketingNav />
      <main className="max-w-3xl mx-auto px-6 py-16 text-gray-300">
        <h1 className="text-3xl font-bold text-white mb-2">Refund Policy</h1>
        <p className="text-sm text-gray-500 mb-10">Last updated: May 15, 2025</p>

        <section className="space-y-8 text-sm leading-relaxed">
          <div>
            <h2 className="text-lg font-semibold text-white mb-2">1. 7-Day Money-Back Guarantee</h2>
            <p>
              If you are not satisfied with your paid subscription, you may request a full refund
              within <strong className="text-white">7 days</strong> of your initial purchase or
              renewal date. Refund requests outside this window will not be honored.
            </p>
          </div>

          <div>
            <h2 className="text-lg font-semibold text-white mb-2">2. How to Request a Refund</h2>
            <p>To request a refund:</p>
            <ol className="list-decimal list-inside mt-2 space-y-1 text-gray-400">
              <li>
                Email{" "}
                <a
                  href="mailto:support@aiworkflowautomator.com"
                  className="text-violet-400 hover:text-violet-300 underline"
                >
                  support@aiworkflowautomator.com
                </a>{" "}
                from the address associated with your account
              </li>
              <li>Include the subject line: "Refund Request"</li>
              <li>Briefly describe the reason for your request</li>
            </ol>
            <p className="mt-3">
              We will process eligible refunds within <strong className="text-white">5–10 business days</strong>.
            </p>
          </div>

          <div>
            <h2 className="text-lg font-semibold text-white mb-2">3. Non-Refundable Situations</h2>
            <p>Refunds will not be issued for:</p>
            <ul className="list-disc list-inside mt-2 space-y-1 text-gray-400">
              <li>Requests made after the 7-day window</li>
              <li>Accounts terminated for violation of our Terms of Service</li>
              <li>Partial billing periods (e.g., mid-cycle cancellations)</li>
              <li>Usage-based charges already incurred</li>
            </ul>
          </div>

          <div>
            <h2 className="text-lg font-semibold text-white mb-2">4. Cancellations</h2>
            <p>
              You may cancel your subscription at any time from your account settings. Cancellation
              stops future charges but does not automatically trigger a refund. Your access continues
              until the end of the current billing period.
            </p>
          </div>

          <div>
            <h2 className="text-lg font-semibold text-white mb-2">5. Payment Method</h2>
            <p>
              Refunds are returned to the original payment method used at purchase. Processing times
              may vary depending on your bank or card provider.
            </p>
          </div>

          <div>
            <h2 className="text-lg font-semibold text-white mb-2">6. Contact</h2>
            <p>
              Questions about this policy? Contact us at{" "}
              <a
                href="mailto:support@aiworkflowautomator.com"
                className="text-violet-400 hover:text-violet-300 underline"
              >
                support@aiworkflowautomator.com
              </a>
              .
            </p>
          </div>
        </section>
      </main>

      <footer className="border-t border-gray-800/60 py-10 mt-10">
        <div className="max-w-5xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-4 text-sm text-gray-500">
          <p>© {new Date().getFullYear()} AI Workflow Automator</p>
          <div className="flex items-center gap-6">
            <Link href="/terms" className="hover:text-gray-300 transition-colors">Terms</Link>
            <Link href="/privacy" className="hover:text-gray-300 transition-colors">Privacy</Link>
            <Link href="/refund" className="hover:text-gray-300 transition-colors">Refunds</Link>
          </div>
        </div>
      </footer>
    </>
  );
}

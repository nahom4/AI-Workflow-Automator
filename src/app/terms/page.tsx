import Link from "next/link";
import MarketingNav from "@/components/MarketingNav";

export const metadata = {
  title: "Terms of Service — AI Workflow Automator",
};

export default function TermsPage() {
  return (
    <>
      <MarketingNav />
      <main className="max-w-3xl mx-auto px-6 py-16 text-gray-300">
        <h1 className="text-3xl font-bold text-white mb-2">Terms of Service</h1>
        <p className="text-sm text-gray-500 mb-10">Last updated: May 15, 2025</p>

        <section className="space-y-8 text-sm leading-relaxed">
          <div>
            <h2 className="text-lg font-semibold text-white mb-2">1. Acceptance of Terms</h2>
            <p>
              By accessing or using AI Workflow Automator ("Service"), you agree to be bound by these
              Terms of Service. If you do not agree, do not use the Service.
            </p>
          </div>

          <div>
            <h2 className="text-lg font-semibold text-white mb-2">2. Description of Service</h2>
            <p>
              AI Workflow Automator provides automated lead discovery, enrichment, and workflow
              automation tools. Features may change at any time without notice.
            </p>
          </div>

          <div>
            <h2 className="text-lg font-semibold text-white mb-2">3. Account Registration</h2>
            <p>
              You must create an account to use the Service. You are responsible for maintaining the
              confidentiality of your credentials and for all activity under your account. You must
              provide accurate, current information and notify us immediately of any unauthorized use.
            </p>
          </div>

          <div>
            <h2 className="text-lg font-semibold text-white mb-2">4. Acceptable Use</h2>
            <p>You agree not to:</p>
            <ul className="list-disc list-inside mt-2 space-y-1 text-gray-400">
              <li>Use the Service for illegal purposes or in violation of any applicable law</li>
              <li>Scrape, harvest, or collect data in violation of third-party terms of service</li>
              <li>Attempt to reverse-engineer, hack, or disrupt the Service</li>
              <li>Resell or sublicense access to the Service without written consent</li>
              <li>Transmit malware, spam, or any harmful content</li>
            </ul>
          </div>

          <div>
            <h2 className="text-lg font-semibold text-white mb-2">5. Subscription and Payment</h2>
            <p>
              Paid plans are billed on a recurring basis. By subscribing, you authorize us to charge
              your payment method on each renewal date. All fees are non-refundable except as stated
              in our{" "}
              <Link href="/refund" className="text-violet-400 hover:text-violet-300 underline">
                Refund Policy
              </Link>
              .
            </p>
          </div>

          <div>
            <h2 className="text-lg font-semibold text-white mb-2">6. Intellectual Property</h2>
            <p>
              All content, software, and technology in the Service is owned by or licensed to us. You
              retain ownership of data you upload or create using the Service.
            </p>
          </div>

          <div>
            <h2 className="text-lg font-semibold text-white mb-2">
              7. Disclaimer of Warranties
            </h2>
            <p>
              The Service is provided "as is" without warranties of any kind, express or implied,
              including merchantability, fitness for a particular purpose, or non-infringement. We do
              not guarantee uninterrupted or error-free operation.
            </p>
          </div>

          <div>
            <h2 className="text-lg font-semibold text-white mb-2">8. Limitation of Liability</h2>
            <p>
              To the maximum extent permitted by law, we are not liable for any indirect, incidental,
              special, or consequential damages arising from your use of the Service, even if advised
              of the possibility of such damages. Our total liability shall not exceed the amount you
              paid in the 12 months preceding the claim.
            </p>
          </div>

          <div>
            <h2 className="text-lg font-semibold text-white mb-2">9. Termination</h2>
            <p>
              We may suspend or terminate your account at any time for violation of these Terms. You
              may cancel your account at any time from your account settings. Upon termination, your
              right to use the Service ceases immediately.
            </p>
          </div>

          <div>
            <h2 className="text-lg font-semibold text-white mb-2">10. Changes to Terms</h2>
            <p>
              We may update these Terms at any time. Continued use of the Service after changes
              constitutes acceptance. We will notify you of material changes via email or in-app
              notice.
            </p>
          </div>

          <div>
            <h2 className="text-lg font-semibold text-white mb-2">11. Contact</h2>
            <p>
              Questions about these Terms? Email us at{" "}
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

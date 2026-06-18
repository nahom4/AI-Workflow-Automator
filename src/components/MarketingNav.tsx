import { auth } from "@/auth";
import Link from "next/link";

export default async function MarketingNav() {
  const session = await auth();
  const user = session?.user;

  return (
    <nav className="sticky top-0 z-50 border-b border-gray-800/60 bg-gray-950/80 backdrop-blur-md">
      <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
        <Link
          href="/"
          className="text-violet-400 font-semibold text-lg tracking-tight hover:text-violet-300 transition-colors"
        >
          AI Workflow Automator
        </Link>

        <div className="flex items-center gap-6">
          <Link
            href="/pricing"
            className="text-sm text-gray-400 hover:text-gray-200 transition-colors hidden sm:block"
          >
            Pricing
          </Link>
          {user ? (
            <Link
              href="/automations"
              className="bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
            >
              Open dashboard
            </Link>
          ) : (
            <>
              <Link
                href="/login"
                className="text-sm text-gray-400 hover:text-gray-200 transition-colors"
              >
                Sign in
              </Link>
              <Link
                href="/signup"
                className="bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
              >
                Get started
              </Link>
            </>
          )}
        </div>
      </div>
    </nav>
  );
}

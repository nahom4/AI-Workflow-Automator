import { auth } from "@/auth";
import SignOutButton from "@/components/SignOutButton";
import Link from "next/link";

export default async function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await auth();
  const user = session?.user;

  return (
    <>
      <nav className="sticky top-0 z-50 border-b border-gray-800 bg-gray-950/90 backdrop-blur-sm px-6 py-4 flex items-center justify-between">
        <Link
          href={user ? "/automations" : "/"}
          className="text-violet-400 font-semibold text-lg tracking-tight hover:text-violet-300 transition-colors"
        >
          AI Workflow Automator
        </Link>

        <div className="flex items-center gap-5">
          <Link
            href="/"
            className="text-sm text-gray-400 hover:text-gray-200 transition-colors hidden sm:block"
          >
            Home
          </Link>
          <Link
            href="/pricing"
            className="text-sm text-gray-400 hover:text-gray-200 transition-colors hidden sm:block"
          >
            Pricing
          </Link>
          {user ? (
            <>
              <Link
                href="/automations/new"
                className="bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
              >
                + New
              </Link>
              <div className="flex items-center gap-3">
                <Link
                  href="/account/billing"
                  className="text-sm text-gray-400 hover:text-gray-200 transition-colors hidden sm:block"
                >
                  {user.name ?? user.email}
                </Link>
                <SignOutButton />
              </div>
            </>
          ) : (
            <Link
              href="/login"
              className="text-sm text-gray-400 hover:text-gray-200 transition-colors"
            >
              Sign in
            </Link>
          )}
        </div>
      </nav>
      <main className="max-w-4xl mx-auto px-6 py-10">{children}</main>
    </>
  );
}

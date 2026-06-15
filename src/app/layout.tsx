import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";
import { auth } from "@/auth";
import SignOutButton from "@/components/SignOutButton";
import Link from "next/link";

const geistSans = localFont({
  src: "./fonts/GeistVF.woff",
  variable: "--font-geist-sans",
  weight: "100 900",
});
const geistMono = localFont({
  src: "./fonts/GeistMonoVF.woff",
  variable: "--font-geist-mono",
  weight: "100 900",
});

export const metadata: Metadata = {
  title: "AI Workflow Automator",
  description: "Describe what to automate. Get reliable leads on a schedule.",
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await auth();
  const user = session?.user;

  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} min-h-screen bg-gray-950 text-gray-100 antialiased`}
      >
        <nav className="sticky top-0 z-50 border-b border-gray-800 bg-gray-950/90 backdrop-blur-sm px-6 py-4 flex items-center justify-between">
          <Link
            href="/automations"
            className="text-violet-400 font-semibold text-lg tracking-tight hover:text-violet-300 transition-colors"
          >
            AI Workflow Automator
          </Link>

          <div className="flex items-center gap-4">
            {user ? (
              <>
                <Link
                  href="/automations/new"
                  className="bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
                >
                  + New
                </Link>
                <div className="flex items-center gap-3">
                  <span className="text-sm text-gray-400 hidden sm:block">
                    {user.name ?? user.email}
                  </span>
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
      </body>
    </html>
  );
}

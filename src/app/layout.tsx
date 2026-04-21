import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";

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
  description: "Describe an automation in plain English. Get a live webhook URL.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} min-h-screen bg-gray-950 text-gray-100 antialiased`}
      >
        <nav className="border-b border-gray-800 px-6 py-4 flex items-center justify-between">
          <a
            href="/automations"
            className="text-violet-400 font-semibold text-lg tracking-tight hover:text-violet-300 transition-colors"
          >
            AI Workflow Automator
          </a>
          <a
            href="/automations/new"
            className="bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
          >
            + New Automation
          </a>
        </nav>
        <main className="max-w-4xl mx-auto px-6 py-10">{children}</main>
      </body>
    </html>
  );
}

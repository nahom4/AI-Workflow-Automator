import { auth } from "@/auth";
import MarketingNav from "@/components/MarketingNav";
import Link from "next/link";

export default async function HomePage() {
  const session = await auth();
  const isSignedIn = !!session?.user;

  return (
    <>
      <MarketingNav />

      <div className="relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-b from-violet-900/20 via-gray-950 to-gray-950 pointer-events-none" />
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[800px] bg-violet-600/10 rounded-full blur-3xl pointer-events-none" />

        <section className="relative max-w-5xl mx-auto px-6 pt-24 pb-20 text-center">
          <div className="inline-flex items-center gap-2 px-3 py-1 mb-6 rounded-full border border-violet-500/30 bg-violet-500/10 text-violet-300 text-xs font-medium">
            <span className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-pulse" />
            Always-on AI research assistant
          </div>

          <h1 className="text-5xl sm:text-6xl md:text-7xl font-bold tracking-tight text-white leading-[1.05]">
            Stop searching.
            <br />
            <span className="bg-gradient-to-r from-violet-400 to-fuchsia-400 bg-clip-text text-transparent">
              Start receiving.
            </span>
          </h1>

          <p className="mt-7 max-w-2xl mx-auto text-lg sm:text-xl text-gray-400 leading-relaxed">
            Describe what you&apos;re looking for once. We watch the sites, score every
            result with AI, and drop only the matches in your inbox or Google Sheet —
            on your schedule, while you sleep.
          </p>

          <div className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link
              href={isSignedIn ? "/automations/new" : "/signup"}
              className="bg-violet-600 hover:bg-violet-500 text-white font-medium px-7 py-3.5 rounded-lg transition-colors text-base shadow-lg shadow-violet-600/20"
            >
              {isSignedIn ? "Create an automation" : "Start free — no card needed"}
            </Link>
            <Link
              href="/pricing"
              className="text-gray-300 hover:text-white font-medium px-7 py-3.5 rounded-lg transition-colors text-base border border-gray-700 hover:border-gray-500"
            >
              See pricing
            </Link>
          </div>

          <p className="mt-6 text-sm text-gray-500">
            Free forever for 3 automations. No credit card.
          </p>
        </section>
      </div>

      <section className="max-w-5xl mx-auto px-6 py-20">
        <div className="text-center mb-14">
          <p className="text-violet-400 text-sm font-medium uppercase tracking-wider mb-3">
            The pain
          </p>
          <h2 className="text-3xl sm:text-4xl font-bold text-white tracking-tight">
            You&apos;re wasting hours hunting for things
            <br />
            you don&apos;t even want.
          </h2>
        </div>

        <div className="grid sm:grid-cols-3 gap-6">
          {[
            {
              icon: "🔄",
              title: "Refreshing the same sites",
              body: "Job boards, scholarship listings, supplier catalogs — checking them every day on the off chance something new shows up.",
            },
            {
              icon: "🗑️",
              title: "Drowning in irrelevance",
              body: "When something does post, 90% of it doesn't match what you actually need. You skim, dismiss, repeat.",
            },
            {
              icon: "⏰",
              title: "Missing the good ones",
              body: "The opportunities you'd actually want? Posted at 2am, filled by lunch. You never even saw them.",
            },
          ].map((p) => (
            <div
              key={p.title}
              className="border border-gray-800 bg-gray-900/30 rounded-xl p-6"
            >
              <div className="text-3xl mb-4">{p.icon}</div>
              <h3 className="font-semibold text-white mb-2">{p.title}</h3>
              <p className="text-sm text-gray-400 leading-relaxed">{p.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="max-w-5xl mx-auto px-6 py-20 border-t border-gray-800/60">
        <div className="text-center mb-14">
          <p className="text-violet-400 text-sm font-medium uppercase tracking-wider mb-3">
            How it works
          </p>
          <h2 className="text-3xl sm:text-4xl font-bold text-white tracking-tight">
            Three steps. Then never again.
          </h2>
        </div>

        <div className="space-y-5">
          {[
            {
              step: "01",
              title: "Tell it what you want",
              body: "Plain English. \"Remote senior Python roles paying over $120k, US-friendly hours.\" Or \"Master&apos;s scholarships in Europe with full tuition coverage.\" Anything.",
            },
            {
              step: "02",
              title: "Pick your sources & schedule",
              body: "Add the sites you'd normally check by hand. Set how often you want it to run — every 2 hours, twice a day, once a week. Your call.",
            },
            {
              step: "03",
              title: "Wake up to the matches",
              body: "We extract every listing, score each one with AI against your criteria, and deliver only what passes your threshold. Email, Gmail, or Google Sheet — your choice.",
            },
          ].map((s) => (
            <div
              key={s.step}
              className="flex gap-6 items-start border border-gray-800 bg-gray-900/30 rounded-xl p-6 hover:border-violet-500/40 transition-colors"
            >
              <div className="text-violet-400 font-mono font-bold text-2xl shrink-0 mt-1">
                {s.step}
              </div>
              <div>
                <h3 className="font-semibold text-white text-lg mb-2">{s.title}</h3>
                <p className="text-gray-400 leading-relaxed">{s.body}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="max-w-5xl mx-auto px-6 py-20 border-t border-gray-800/60">
        <div className="text-center mb-14">
          <p className="text-violet-400 text-sm font-medium uppercase tracking-wider mb-3">
            What you get
          </p>
          <h2 className="text-3xl sm:text-4xl font-bold text-white tracking-tight">
            Built to actually save you time.
          </h2>
        </div>

        <div className="grid sm:grid-cols-2 gap-5">
          {[
            {
              title: "AI-scored relevance",
              body: "Every result gets a 1–10 score against your criteria. Set a threshold, never see junk again.",
            },
            {
              title: "Works on almost any site",
              body: "Three-tier extraction handles APIs, dynamic sites, and even pages that hide their data behind JavaScript.",
            },
            {
              title: "Google Sheets sync",
              body: "Pipe matches straight into a sheet. Track them, share them, run your own analysis.",
            },
            {
              title: "Gmail digest",
              body: "A clean daily summary in your inbox. Read it with coffee, act on what matters.",
            },
            {
              title: "Resume-aware ranking",
              body: "Upload your CV or company profile. The AI uses it as context when grading every lead.",
            },
            {
              title: "Set the cadence",
              body: "Every 2 hours, twice daily, weekly — whatever matches the freshness you need.",
            },
          ].map((f) => (
            <div
              key={f.title}
              className="border border-gray-800 bg-gray-900/30 rounded-xl p-6"
            >
              <div className="flex items-start gap-3">
                <div className="w-1.5 h-1.5 rounded-full bg-violet-400 mt-2.5 shrink-0" />
                <div>
                  <h3 className="font-semibold text-white mb-1.5">{f.title}</h3>
                  <p className="text-sm text-gray-400 leading-relaxed">{f.body}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="max-w-5xl mx-auto px-6 py-20 border-t border-gray-800/60">
        <div className="text-center mb-14">
          <p className="text-violet-400 text-sm font-medium uppercase tracking-wider mb-3">
            Who it&apos;s for
          </p>
          <h2 className="text-3xl sm:text-4xl font-bold text-white tracking-tight">
            If you check a list every day, this replaces that.
          </h2>
        </div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
          {[
            { icon: "💼", title: "Job seekers", body: "Track new roles on niche boards. Match by salary, stack, remote policy." },
            { icon: "🎓", title: "Scholarship hunters", body: "Monitor university pages and aggregators. Filter by country, level, funding." },
            { icon: "🛒", title: "Deal hunters", body: "Watch marketplaces for items hitting your price. Get pinged when one lands." },
            { icon: "📈", title: "Freelancers", body: "Scan Upwork, RemoteOK, and others for clients that fit your niche." },
          ].map((u) => (
            <div
              key={u.title}
              className="border border-gray-800 bg-gray-900/30 rounded-xl p-5"
            >
              <div className="text-3xl mb-3">{u.icon}</div>
              <h3 className="font-semibold text-white mb-1.5">{u.title}</h3>
              <p className="text-sm text-gray-400 leading-relaxed">{u.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="max-w-5xl mx-auto px-6 py-20 border-t border-gray-800/60">
        <div className="relative overflow-hidden rounded-2xl border border-violet-500/30 bg-gradient-to-br from-violet-900/30 to-fuchsia-900/20 p-10 sm:p-14 text-center">
          <h2 className="text-3xl sm:text-4xl font-bold text-white tracking-tight">
            Set it up once. Get back hours every week.
          </h2>
          <p className="mt-4 text-gray-300 max-w-xl mx-auto">
            Free to start. No card. Upgrade when you want more automations or sharper AI.
          </p>
          <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link
              href={isSignedIn ? "/automations/new" : "/signup"}
              className="bg-violet-600 hover:bg-violet-500 text-white font-medium px-7 py-3.5 rounded-lg transition-colors text-base shadow-lg shadow-violet-600/30"
            >
              {isSignedIn ? "Create your first automation" : "Create your free account"}
            </Link>
            <Link
              href="/pricing"
              className="text-gray-200 hover:text-white font-medium px-7 py-3.5 rounded-lg transition-colors text-base"
            >
              View pricing →
            </Link>
          </div>
        </div>
      </section>

      <footer className="border-t border-gray-800/60 py-10 mt-10">
        <div className="max-w-5xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-4 text-sm text-gray-500">
          <p>© {new Date().getFullYear()} AI Workflow Automator</p>
          <div className="flex items-center gap-6">
            <Link href="/pricing" className="hover:text-gray-300 transition-colors">
              Pricing
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

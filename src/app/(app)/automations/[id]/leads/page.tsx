import { db, initDb } from "@/lib/db";
import { AutomationRow, LeadRow } from "@/types/db";
import { notFound } from "next/navigation";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default async function LeadsPage({
  params,
  searchParams,
}: {
  params: { id: string };
  searchParams: { page?: string };
}) {
  await initDb();

  const PAGE_SIZE = 50;
  const page = Math.max(1, parseInt(searchParams.page ?? "1", 10));
  const offset = (page - 1) * PAGE_SIZE;

  const [autoResult, leadsResult, countResult] = await Promise.all([
    db().execute({ sql: "SELECT id, name FROM automations WHERE id = ?", args: [params.id] }),
    db().execute({
      sql: "SELECT * FROM leads WHERE automation_id = ? ORDER BY score DESC, created_at DESC LIMIT ? OFFSET ?",
      args: [params.id, PAGE_SIZE, offset],
    }),
    db().execute({
      sql: "SELECT COUNT(*) as count FROM leads WHERE automation_id = ?",
      args: [params.id],
    }),
  ]);

  const automation = autoResult.rows[0] as unknown as Pick<AutomationRow, "id" | "name"> | undefined;
  if (!automation) notFound();

  const leads = leadsResult.rows as unknown as LeadRow[];
  const total = Number((countResult.rows[0] as unknown as { count: number }).count ?? 0);
  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <Link
          href={`/automations/${params.id}`}
          className="text-sm text-gray-500 hover:text-gray-300 transition-colors"
        >
          ← {automation.name}
        </Link>
        <h1 className="text-2xl font-bold text-gray-100 mt-2">
          All Leads
        </h1>
        <p className="text-gray-400 text-sm mt-1">
          {total} lead{total !== 1 ? "s" : ""} · sorted by score
        </p>
      </div>

      {leads.length === 0 ? (
        <p className="text-gray-600 text-sm">No leads yet.</p>
      ) : (
        <div className="space-y-2">
          {leads.map((lead) => (
            <a
              key={lead.id}
              href={lead.url}
              target="_blank"
              rel="noopener noreferrer"
              className="block bg-gray-900 border border-gray-800 rounded-lg p-3 hover:border-violet-700 transition-colors"
            >
              <div className="flex items-start justify-between gap-3">
                <p className="text-sm text-gray-200 font-medium">{lead.title}</p>
                <span className="text-xs font-bold text-violet-400 flex-shrink-0">
                  {lead.score.toFixed(1)}
                </span>
              </div>
              <div className="flex items-center gap-3 mt-1">
                <p className="text-xs text-gray-500">{lead.source_domain}</p>
                {lead.matched_reasons && (
                  <p className="text-xs text-gray-600 truncate">{lead.matched_reasons}</p>
                )}
              </div>
            </a>
          ))}
        </div>
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-between pt-2">
          {page > 1 ? (
            <Link
              href={`/automations/${params.id}/leads?page=${page - 1}`}
              className="text-xs text-violet-400 hover:text-violet-300"
            >
              ← Previous
            </Link>
          ) : (
            <span />
          )}
          <span className="text-xs text-gray-600">
            Page {page} of {totalPages}
          </span>
          {page < totalPages ? (
            <Link
              href={`/automations/${params.id}/leads?page=${page + 1}`}
              className="text-xs text-violet-400 hover:text-violet-300"
            >
              Next →
            </Link>
          ) : (
            <span />
          )}
        </div>
      )}
    </div>
  );
}

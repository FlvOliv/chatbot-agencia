import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { listLeads } from "@/lib/api";
import type { LeadTemp } from "@/lib/types";
import { LeadsFilters } from "@/components/leads/leads-filters";
import { LoadMore } from "@/components/leads/load-more";
import { TempBadge } from "@/components/temp-badge";
import { formatPhone, relativeFromNow } from "@/lib/format";

export const dynamic = "force-dynamic";

const TEMP_VALUES: LeadTemp[] = ["frio", "morno", "quente", "urgente"];

function asTemp(v: string | undefined): LeadTemp | undefined {
  return TEMP_VALUES.includes(v as LeadTemp) ? (v as LeadTemp) : undefined;
}

type LeadsSearchParams = Promise<{
  temp?: string | string[];
  q?: string | string[];
  page_size?: string | string[];
}>;

export default async function LeadsPage({
  searchParams,
}: {
  searchParams: LeadsSearchParams;
}) {
  const sp = await searchParams;
  const temp = asTemp(typeof sp.temp === "string" ? sp.temp : undefined);
  const q = typeof sp.q === "string" ? sp.q : undefined;
  const pageSizeRaw = typeof sp.page_size === "string" ? Number(sp.page_size) : 20;
  const pageSize = Number.isFinite(pageSizeRaw) ? Math.min(Math.max(pageSizeRaw, 1), 100) : 20;

  const data = await listLeads({ temp, q, page: 1, page_size: pageSize });
  const items = data?.items ?? [];
  const total = data?.total ?? 0;

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl sm:text-2xl font-semibold tracking-tight">Leads</h1>
        <p className="mt-0.5 text-sm text-zinc-500 dark:text-zinc-400">
          {total} {total === 1 ? "lead encontrado" : "leads encontrados"}
        </p>
      </header>

      <LeadsFilters />

      {/* Mobile: cards. Desktop: table. */}
      <div className="space-y-2 sm:hidden">
        {items.length === 0 ? (
          <EmptyState />
        ) : (
          items.map((lead) => {
            const display = lead.name?.trim() || formatPhone(lead.phone);
            const dest = lead.destination?.trim() || "Destino não informado";
            return (
              <Link
                key={lead.id}
                href={`/leads/${encodeURIComponent(lead.phone)}`}
                className="group flex items-center gap-3 rounded-lg border border-zinc-200 bg-white p-3 transition-colors active:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-950 min-h-11"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="truncate text-sm font-medium">{display}</p>
                    <TempBadge temp={lead.lead_temp} />
                  </div>
                  <p className="mt-0.5 truncate text-xs text-zinc-500 dark:text-zinc-400">
                    {dest}
                  </p>
                  <p className="mt-0.5 text-[11px] text-zinc-400">
                    {formatPhone(lead.phone)} · {relativeFromNow(lead.created_at)}
                  </p>
                </div>
                <ChevronRight className="size-4 shrink-0 text-zinc-400" />
              </Link>
            );
          })
        )}
      </div>

      <div className="hidden sm:block">
        {items.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="overflow-hidden rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
            <table className="w-full text-sm">
              <thead className="bg-zinc-50 text-xs uppercase tracking-wide text-zinc-500 dark:bg-zinc-900 dark:text-zinc-400">
                <tr>
                  <th className="px-4 py-2 text-left font-medium">Nome</th>
                  <th className="px-4 py-2 text-left font-medium">Telefone</th>
                  <th className="px-4 py-2 text-left font-medium">Destino</th>
                  <th className="px-4 py-2 text-left font-medium">Temp.</th>
                  <th className="px-4 py-2 text-left font-medium">Quando</th>
                  <th className="w-8" />
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
                {items.map((lead) => (
                  <tr
                    key={lead.id}
                    className="hover:bg-zinc-50 dark:hover:bg-zinc-900"
                  >
                    <td className="px-4 py-3">
                      <Link
                        href={`/leads/${encodeURIComponent(lead.phone)}`}
                        className="font-medium hover:underline"
                      >
                        {lead.name?.trim() || "—"}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-zinc-600 dark:text-zinc-400 tabular-nums">
                      {formatPhone(lead.phone)}
                    </td>
                    <td className="px-4 py-3 text-zinc-600 dark:text-zinc-400">
                      {lead.destination?.trim() || "—"}
                    </td>
                    <td className="px-4 py-3">
                      <TempBadge temp={lead.lead_temp} />
                    </td>
                    <td className="px-4 py-3 text-zinc-500 dark:text-zinc-500 text-xs">
                      {relativeFromNow(lead.created_at)}
                    </td>
                    <td className="px-2">
                      <Link
                        href={`/leads/${encodeURIComponent(lead.phone)}`}
                        aria-label="Abrir lead"
                        className="inline-flex size-8 items-center justify-center rounded-md text-zinc-400 hover:bg-zinc-100 hover:text-zinc-900 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
                      >
                        <ChevronRight className="size-4" />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <LoadMore currentSize={items.length} total={total} />
    </div>
  );
}

function EmptyState() {
  return (
    <div className="rounded-lg border border-dashed border-zinc-300 bg-white p-8 text-center text-sm text-zinc-500 dark:border-zinc-700 dark:bg-zinc-950">
      Nenhum lead encontrado com esses filtros.
    </div>
  );
}

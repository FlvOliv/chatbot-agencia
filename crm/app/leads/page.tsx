import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { listLeads } from "@/lib/api";
import type { LeadTemp } from "@/lib/types";
import { LeadsFilters } from "@/components/leads/leads-filters";
import { NewLeadButton } from "@/components/leads/new-lead-button";
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
  sort?: string | string[];
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
  const sort = sp.sort === "oldest" ? "oldest" : "recent";
  const pageSizeRaw = typeof sp.page_size === "string" ? Number(sp.page_size) : 20;
  const pageSize = Number.isFinite(pageSizeRaw) ? Math.min(Math.max(pageSizeRaw, 1), 100) : 20;

  const data = await listLeads({ temp, q, sort, page: 1, page_size: pageSize });
  const items = data?.items ?? [];
  const total = data?.total ?? 0;

  return (
    <div className="space-y-4">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h1 className="font-heading text-2xl sm:text-3xl font-semibold tracking-tight">
            Leads
          </h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {total} {total === 1 ? "lead encontrado" : "leads encontrados"}
          </p>
        </div>
        <NewLeadButton />
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
                href={`/leads/${lead.numero}`}
                className="group flex items-center gap-3 rounded-lg border border-border bg-card p-3 transition-colors active:bg-accent/50 min-h-11"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="truncate text-sm font-medium">{display}</p>
                    <TempBadge temp={lead.lead_temp} />
                  </div>
                  <p className="mt-0.5 truncate text-xs text-muted-foreground">
                    {dest}
                  </p>
                  <p className="mt-0.5 text-[11px] text-muted-foreground/80">
                    {lead.numero ? `#${lead.numero} · ` : ""}
                    {formatPhone(lead.phone)} · {relativeFromNow(lead.created_at)}
                  </p>
                </div>
                <ChevronRight className="size-4 shrink-0 text-muted-foreground/70" />
              </Link>
            );
          })
        )}
      </div>

      <div className="hidden sm:block">
        {items.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="overflow-hidden rounded-lg border border-border bg-card shadow-sm">
            <table className="w-full text-sm">
              <thead className="bg-muted/60 text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="px-4 py-2 text-left font-medium">Protocolo</th>
                  <th className="px-4 py-2 text-left font-medium">Nome</th>
                  <th className="px-4 py-2 text-left font-medium">Telefone</th>
                  <th className="px-4 py-2 text-left font-medium">Destino</th>
                  <th className="px-4 py-2 text-left font-medium">Temp.</th>
                  <th className="px-4 py-2 text-left font-medium">Quando</th>
                  <th className="w-8" />
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {items.map((lead) => (
                  <tr key={lead.id} className="hover:bg-accent/40">
                    <td className="px-4 py-3 text-muted-foreground tabular-nums">
                      {lead.numero ? `#${lead.numero}` : "—"}
                    </td>
                    <td className="px-4 py-3">
                      <Link
                        href={`/leads/${lead.numero}`}
                        className="font-medium hover:underline"
                      >
                        {lead.name?.trim() || "—"}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground tabular-nums">
                      {formatPhone(lead.phone)}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {lead.destination?.trim() || "—"}
                    </td>
                    <td className="px-4 py-3">
                      <TempBadge temp={lead.lead_temp} />
                    </td>
                    <td className="px-4 py-3 text-muted-foreground/80 text-xs">
                      {relativeFromNow(lead.created_at)}
                    </td>
                    <td className="px-2">
                      <Link
                        href={`/leads/${lead.numero}`}
                        aria-label="Abrir lead"
                        className="inline-flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-accent-foreground"
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
    <div className="rounded-lg border border-dashed border-border bg-card p-8 text-center text-sm text-muted-foreground">
      Nenhum lead encontrado com esses filtros.
    </div>
  );
}

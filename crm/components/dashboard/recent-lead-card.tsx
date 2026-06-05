import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { TempBadge } from "@/components/temp-badge";
import { formatPhone, relativeFromNow } from "@/lib/format";
import type { LeadListItem } from "@/lib/types";

export function RecentLeadCard({ lead }: { lead: LeadListItem }) {
  const display = lead.name?.trim() || formatPhone(lead.phone);
  const dest = lead.destination?.trim() || "Destino não informado";
  return (
    <Link
      href={`/leads/${encodeURIComponent(lead.phone)}`}
      className="group flex items-center gap-3 rounded-lg border border-zinc-200 bg-white p-3 transition-colors hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-950 dark:hover:bg-zinc-900 min-h-11"
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="truncate text-sm font-medium">{display}</p>
          <TempBadge temp={lead.lead_temp} />
        </div>
        <p className="mt-0.5 truncate text-xs text-zinc-500 dark:text-zinc-400">
          {dest} · {relativeFromNow(lead.created_at)}
        </p>
      </div>
      <ChevronRight className="size-4 shrink-0 text-zinc-400 transition-transform group-hover:translate-x-0.5" />
    </Link>
  );
}

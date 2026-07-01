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
      href={`/leads/${lead.numero}`}
      className="group flex items-center gap-3 rounded-lg border border-border bg-card p-3 transition-colors hover:bg-accent/50 min-h-11"
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="truncate text-sm font-medium">{display}</p>
          <TempBadge temp={lead.lead_temp} />
        </div>
        <p className="mt-0.5 truncate text-xs text-muted-foreground">
          {dest} · {relativeFromNow(lead.created_at)}
        </p>
      </div>
      <ChevronRight className="size-4 shrink-0 text-muted-foreground/70 transition-transform group-hover:translate-x-0.5" />
    </Link>
  );
}

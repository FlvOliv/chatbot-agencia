import Link from "next/link";
import { MessageCircle } from "lucide-react";

import { listConversations } from "@/lib/api";
import { TempBadge } from "@/components/temp-badge";

export const dynamic = "force-dynamic";

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const min = Math.floor(diff / 60000);
  if (min < 1) return "agora";
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h} h`;
  return `${Math.floor(h / 24)} d`;
}

export default async function ConversasPage() {
  const conversas = await listConversations();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Conversas</h1>
        <p className="text-sm text-zinc-500">
          Acompanhe os atendimentos da Malu e assuma quando quiser.
        </p>
      </div>

      {conversas.length === 0 ? (
        <div className="rounded-xl border border-dashed border-zinc-300 dark:border-zinc-700 p-10 text-center text-sm text-zinc-500">
          Nenhuma conversa ainda. Quando um cliente falar com a Malu, aparece
          aqui.
        </div>
      ) : (
        <ul className="space-y-2">
          {conversas.map((c) => (
            <li key={c.phone}>
              <Link
                href={`/conversas/${encodeURIComponent(c.phone)}`}
                className="flex items-center gap-3 rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 p-4 hover:border-zinc-300 dark:hover:border-zinc-700 transition-colors"
              >
                <div className="size-10 shrink-0 grid place-items-center rounded-full bg-zinc-100 dark:bg-zinc-900 text-zinc-500">
                  <MessageCircle className="size-5" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium truncate">
                      {c.customer_name ?? c.phone}
                    </span>
                    {c.lead_temp ? <TempBadge temp={c.lead_temp} /> : null}
                  </div>
                  <p className="text-sm text-zinc-500 truncate">
                    {c.last_message_preview || "—"}
                  </p>
                </div>
                <div className="shrink-0 text-right">
                  <div className="text-xs text-zinc-400">
                    {timeAgo(c.last_message_at)}
                  </div>
                  <div className="text-xs text-zinc-400">
                    {c.message_count} msgs
                  </div>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

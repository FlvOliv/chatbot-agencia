import Link from "next/link";
import { ArrowLeft } from "lucide-react";

import {
  getConversation,
  getConversationState,
  getLead,
  listConversations,
} from "@/lib/api";
import { ConversaWorkspace } from "@/components/conversas/conversa-workspace";
import { ConversationList } from "@/components/conversas/conversation-list";
import { AutoRefresh } from "@/components/auto-refresh";

export const dynamic = "force-dynamic";

export default async function ConversaDetailPage({
  params,
}: {
  params: Promise<{ phone: string }>;
}) {
  const { phone } = await params;
  const decoded = decodeURIComponent(phone);

  const [conv, state, conversas, lead] = await Promise.all([
    getConversation(decoded),
    getConversationState(decoded),
    listConversations({}),
    getLead(decoded),
  ]);

  return (
    <div className="space-y-3">
      <AutoRefresh intervalMs={6000} />

      <Link
        href="/conversas"
        className="inline-flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-900 md:hidden dark:hover:text-zinc-100"
      >
        <ArrowLeft className="size-4" /> Conversas
      </Link>

      <div className="flex h-[calc(100dvh-9rem)] min-h-[480px] overflow-hidden rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
        {/* Painel 1 — lista */}
        <aside className="hidden w-[280px] shrink-0 flex-col overflow-y-auto border-r border-zinc-200 md:flex dark:border-zinc-800">
          <div className="border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
            <p className="text-sm font-semibold">Conversas</p>
          </div>
          <ConversationList conversations={conversas} activePhone={decoded} />
        </aside>

        {/* Painéis 2 e 3 — thread + lead (com toggle) */}
        {conv === null ? (
          <div className="grid min-w-0 flex-1 place-items-center p-10 text-center text-sm text-zinc-500">
            Conversa não encontrada.
          </div>
        ) : (
          <ConversaWorkspace
            conv={conv}
            initialPaused={state.bot_paused}
            lead={lead}
            phone={decoded}
          />
        )}
      </div>
    </div>
  );
}

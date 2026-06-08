import Link from "next/link";
import { ArrowLeft } from "lucide-react";

import { getConversation, getConversationState } from "@/lib/api";
import { ConversaView } from "@/components/conversas/conversa-view";

export const dynamic = "force-dynamic";

export default async function ConversaDetailPage({
  params,
}: {
  params: Promise<{ phone: string }>;
}) {
  const { phone } = await params;
  const decoded = decodeURIComponent(phone);

  const [conv, state] = await Promise.all([
    getConversation(decoded),
    getConversationState(decoded),
  ]);

  return (
    <div className="space-y-4">
      <Link
        href="/conversas"
        className="inline-flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
      >
        <ArrowLeft className="size-4" />
        Conversas
      </Link>

      {conv === null ? (
        <div className="rounded-xl border border-dashed border-zinc-300 dark:border-zinc-700 p-10 text-center text-sm text-zinc-500">
          Conversa não encontrada.
        </div>
      ) : (
        <ConversaView conv={conv} initialPaused={state.bot_paused} />
      )}
    </div>
  );
}

import { listConversations } from "@/lib/api";
import { AutoRefresh } from "@/components/auto-refresh";
import { ConversasSearch } from "@/components/conversas/conversas-search";
import { ConversationList } from "@/components/conversas/conversation-list";

export const dynamic = "force-dynamic";

export default async function ConversasPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string | string[] }>;
}) {
  const sp = await searchParams;
  const q = typeof sp.q === "string" ? sp.q : undefined;
  const conversas = await listConversations({ q });

  return (
    <div className="space-y-4">
      <AutoRefresh intervalMs={8000} />
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Conversas</h1>
        <p className="text-sm text-zinc-500">
          Acompanhe os atendimentos da Malu e assuma quando quiser.
        </p>
      </div>

      <ConversasSearch />

      {conversas.length === 0 ? (
        <div className="rounded-xl border border-dashed border-zinc-300 p-10 text-center text-sm text-zinc-500 dark:border-zinc-700">
          {q
            ? "Nenhuma conversa encontrada para essa busca."
            : "Nenhuma conversa ainda. Quando um cliente falar com a Malu, aparece aqui."}
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
          <ConversationList conversations={conversas} />
        </div>
      )}
    </div>
  );
}

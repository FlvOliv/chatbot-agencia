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
        <h1 className="font-heading text-2xl sm:text-3xl font-semibold tracking-tight">
          Conversas
        </h1>
        <p className="text-sm text-muted-foreground">
          Acompanhe os atendimentos da Malu e assuma quando quiser.
        </p>
      </div>

      <ConversasSearch />

      {conversas.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border p-10 text-center text-sm text-muted-foreground">
          {q
            ? "Nenhuma conversa encontrada para essa busca."
            : "Nenhuma conversa ainda. Quando um cliente falar com a Malu, aparece aqui."}
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
          <ConversationList conversations={conversas} />
        </div>
      )}
    </div>
  );
}

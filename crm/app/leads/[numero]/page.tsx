import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, Phone } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { getConversation, getLeadByNumero } from "@/lib/api";
import { TempBadge } from "@/components/temp-badge";
import { MessageBubble } from "@/components/leads/message-bubble";
import { DeleteLeadButton } from "@/components/leads/delete-lead-button";
import { Card, CardContent } from "@/components/ui/card";
import { formatPhone } from "@/lib/format";

export const dynamic = "force-dynamic";

type LeadDetailParams = Promise<{ numero: string }>;

export default async function LeadDetailPage({
  params,
}: {
  params: LeadDetailParams;
}) {
  const { numero } = await params;

  // Abre a cotação pelo número (#1001...). Um mesmo cliente pode ter várias.
  const detail = await getLeadByNumero(numero);
  if (!detail) notFound();

  const { lead } = detail;
  const conversation = await getConversation(lead.phone, 100);

  const display =
    lead.name?.trim() ||
    detail.cliente?.profile_name?.trim() ||
    formatPhone(lead.phone);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <Link
            href="/leads"
            className="inline-flex items-center gap-1 text-xs font-medium text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
          >
            <ArrowLeft className="size-3.5" /> Voltar para leads
          </Link>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <h1 className="text-xl sm:text-2xl font-semibold tracking-tight truncate">
              {display}
            </h1>
            <TempBadge temp={lead.lead_temp} />
            {lead.numero && (
              <span className="rounded-md bg-zinc-100 px-2 py-0.5 text-xs font-medium tabular-nums text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
                #{lead.numero}
              </span>
            )}
          </div>
          <p className="mt-1 flex items-center gap-1.5 text-xs text-zinc-500">
            <Phone className="size-3.5" />
            <span className="tabular-nums">{formatPhone(lead.phone)}</span>
            {lead.destination && (
              <>
                <span aria-hidden> · </span>
                <span>{lead.destination}</span>
              </>
            )}
          </p>
        </div>
        {lead.numero && (
          <DeleteLeadButton numero={lead.numero} label={display} />
        )}
      </div>

      {/* Briefing */}
      <Card className="border-zinc-200 dark:border-zinc-800 shadow-none">
        <CardContent className="p-4 sm:p-6">
          <h2 className="text-sm font-semibold text-zinc-500 uppercase tracking-wide mb-3">
            Briefing
          </h2>
          {lead.briefing_md ? (
            <div className="briefing-md text-sm sm:text-[15px] leading-relaxed text-zinc-700 dark:text-zinc-300">
              <ReactMarkdown>{lead.briefing_md}</ReactMarkdown>
            </div>
          ) : (
            <p className="text-sm text-zinc-500">
              A Malu ainda não fechou o briefing desta cotação.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Conversation */}
      <div>
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="text-sm font-semibold">Histórico de conversa</h2>
          <span className="text-xs text-zinc-500">
            {conversation?.messages.length ?? 0} mensagens
          </span>
        </div>

        {conversation && conversation.messages.length > 0 ? (
          <div className="space-y-3 rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
            {conversation.messages.map((m) => (
              <MessageBubble
                key={m.id}
                role={m.role}
                content={m.content}
                createdAt={m.created_at}
              />
            ))}
          </div>
        ) : (
          <div className="rounded-lg border border-dashed border-zinc-300 bg-white p-6 text-center text-sm text-zinc-500 dark:border-zinc-700 dark:bg-zinc-950">
            Sem mensagens registradas ainda.
          </div>
        )}
      </div>
    </div>
  );
}

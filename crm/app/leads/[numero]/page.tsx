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
            className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="size-3.5" /> Voltar para leads
          </Link>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <h1 className="font-heading text-2xl sm:text-3xl font-semibold tracking-tight truncate">
              {display}
            </h1>
            <TempBadge temp={lead.lead_temp} />
            {lead.numero && (
              <span className="rounded-md bg-muted px-2 py-0.5 text-xs font-medium tabular-nums text-muted-foreground">
                #{lead.numero}
              </span>
            )}
          </div>
          <p className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
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
      <Card className="shadow-sm">
        <CardContent className="p-4 sm:p-6">
          <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-3">
            Briefing
          </h2>
          {lead.briefing_md ? (
            <div className="briefing-md text-sm sm:text-[15px] leading-relaxed text-foreground/90">
              <ReactMarkdown>{lead.briefing_md}</ReactMarkdown>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              A Malu ainda não fechou o briefing desta cotação.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Conversation */}
      <div>
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="text-sm font-semibold">Histórico de conversa</h2>
          <span className="text-xs text-muted-foreground">
            {conversation?.messages.length ?? 0} mensagens
          </span>
        </div>

        {conversation && conversation.messages.length > 0 ? (
          <div className="space-y-3 rounded-lg border border-border bg-card p-4 shadow-sm">
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
          <div className="rounded-lg border border-dashed border-border bg-card p-6 text-center text-sm text-muted-foreground">
            Sem mensagens registradas ainda.
          </div>
        )}
      </div>
    </div>
  );
}

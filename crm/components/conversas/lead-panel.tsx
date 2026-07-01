"use client";

import { useState } from "react";
import Link from "next/link";
import { ExternalLink, Copy, Check, FileText } from "lucide-react";

import type { LeadDetail } from "@/lib/types";
import { formatPhone } from "@/lib/format";
import { Avatar } from "./avatar";
import { TempBadge } from "@/components/temp-badge";

function val(raw: Record<string, unknown>, key: string): string | null {
  const v = raw[key];
  if (v === null || v === undefined) return null;
  const s = String(v).trim();
  if (!s || /^n[aã]o informado$/i.test(s) || s === "—") return null;
  return s;
}

function passageiros(raw: Record<string, unknown>): string | null {
  const ad = val(raw, "qtd_adultos");
  const cr = val(raw, "qtd_criancas");
  const parts: string[] = [];
  if (ad) parts.push(`${ad} adulto${ad === "1" ? "" : "s"}`);
  if (cr && cr !== "0") parts.push(`${cr} criança${cr === "1" ? "" : "s"}`);
  return parts.length ? parts.join(" + ") : null;
}

function datas(raw: Record<string, unknown>): string | null {
  const ida = val(raw, "data_ida");
  const volta = val(raw, "data_volta");
  if (ida && volta) return `${ida} – ${volta}`;
  return ida || volta || null;
}

export function LeadPanel({ lead: detail }: { lead: LeadDetail | null }) {
  const [copied, setCopied] = useState(false);

  if (!detail) {
    return (
      <div className="p-5 text-center">
        <div className="mx-auto mb-3 grid size-10 place-items-center rounded-full bg-muted text-muted-foreground">
          <FileText className="size-5" />
        </div>
        <p className="text-sm font-medium">Sem lead ainda</p>
        <p className="mt-1 text-xs text-muted-foreground">
          A Malu monta o briefing quando o cliente termina a coleta.
        </p>
      </div>
    );
  }

  const lead = detail.lead;
  const raw = lead.raw_data ?? {};
  const name =
    lead.name?.trim() ||
    detail.cliente?.profile_name?.trim() ||
    formatPhone(lead.phone);
  const origem = val(raw, "origem");
  const destino = lead.destination?.trim() || val(raw, "destino");
  const rota = origem && destino ? `${origem} → ${destino}` : destino || origem;

  const fields: Array<[string, string | null]> = [
    ["Tipo", lead.travel_type?.trim() || val(raw, "tipo_atendimento")],
    ["Datas", datas(raw)],
    ["Passageiros", passageiros(raw)],
    ["Hospedagem", val(raw, "tipo_hospedagem") || val(raw, "hospedagem_incluida")],
    ["Orçamento", val(raw, "orcamento")],
    ["Pagamento", val(raw, "forma_pagamento")],
    ["Prazo", val(raw, "prazo_decisao")],
    ["Motivo", val(raw, "motivo_viagem")],
    ["Indicação", lead.indicado_por?.trim() || val(raw, "indicado_por")],
  ];
  const shown = fields.filter(([, v]) => v);

  function copyBriefing() {
    if (!lead.briefing_md) return;
    // WhatsApp usa * simples pra negrito; ** (markdown) aparece literal ao colar.
    const text = lead.briefing_md.replace(/\*\*/g, "*");
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  return (
    <div className="flex h-full flex-col">
      <div className="px-5 pt-5 pb-4 text-center">
        <Avatar name={name} size={56} className="mx-auto mb-2" />
        <p className="text-sm font-semibold">{name}</p>
        {rota ? (
          <p className="mt-0.5 text-xs text-muted-foreground">{rota}</p>
        ) : null}
        <div className="mt-2 flex items-center justify-center gap-1.5">
          {lead.numero ? (
            <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium tabular-nums text-muted-foreground">
              #{lead.numero}
            </span>
          ) : null}
          {lead.lead_temp ? <TempBadge temp={lead.lead_temp} /> : null}
        </div>
      </div>

      {shown.length > 0 ? (
        <div className="space-y-2.5 border-t border-border px-5 py-4">
          {shown.map(([label, value]) => (
            <div key={label} className="flex items-start justify-between gap-3">
              <span className="shrink-0 text-xs text-muted-foreground">{label}</span>
              <span className="text-right text-xs font-medium">{value}</span>
            </div>
          ))}
        </div>
      ) : null}

      <div className="mt-auto space-y-2 border-t border-border px-5 py-4">
        <Link
          href={`/leads/${lead.numero}`}
          className="flex items-center justify-center gap-1.5 rounded-lg border border-border px-3 py-2 text-sm font-medium hover:bg-accent"
        >
          <ExternalLink className="size-4" /> Ver lead completo
        </Link>
        {lead.briefing_md ? (
          <button
            onClick={copyBriefing}
            className="flex w-full items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs text-muted-foreground hover:bg-accent"
          >
            {copied ? (
              <>
                <Check className="size-3.5" /> Copiado!
              </>
            ) : (
              <>
                <Copy className="size-3.5" /> Copiar briefing
              </>
            )}
          </button>
        ) : null}
      </div>
    </div>
  );
}

"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { ExternalLink, Copy, Check, FileText, Plus, X, Tag as TagIcon } from "lucide-react";

import type { LeadDetail, Tag } from "@/lib/types";
import { addTagToConversation, removeTagFromConversation, createTag } from "@/lib/actions";
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

// ---------------------------------------------------------------------------
// TagSelector
// ---------------------------------------------------------------------------

function TagSelector({
  phone,
  currentTags,
  allTags,
}: {
  phone: string;
  currentTags: Tag[];
  allTags: Tag[];
}) {
  const [tags, setTags] = useState<Tag[]>(currentTags);
  const [open, setOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newColor, setNewColor] = useState("#6b7280");
  const [creating, setCreating] = useState(false);
  const [loading, setLoading] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Fecha ao clicar fora
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
        setCreating(false);
      }
    }
    if (open) document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const currentIds = new Set(tags.map((t) => t.id));
  const available = allTags.filter((t) => !currentIds.has(t.id));

  async function handleAdd(tag: Tag) {
    setLoading(tag.id);
    try {
      await addTagToConversation(phone, tag.id);
      setTags((prev) => [...prev, tag]);
    } finally {
      setLoading(null);
      if (available.length <= 1) setOpen(false);
    }
  }

  async function handleRemove(tagId: string) {
    setLoading(tagId);
    try {
      await removeTagFromConversation(phone, tagId);
      setTags((prev) => prev.filter((t) => t.id !== tagId));
    } finally {
      setLoading(null);
    }
  }

  async function handleCreate() {
    if (!newName.trim()) return;
    setLoading("new");
    try {
      const tag = await createTag(newName.trim(), newColor);
      await addTagToConversation(phone, tag.id);
      setTags((prev) => [...prev, tag]);
      setNewName("");
      setNewColor("#6b7280");
      setCreating(false);
      setOpen(false);
    } finally {
      setLoading(null);
    }
  }

  return (
    <div className="relative" ref={containerRef}>
      {/* Tags atuais */}
      <div className="flex flex-wrap gap-1.5">
        {tags.map((tag) => (
          <span
            key={tag.id}
            className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium text-white"
            style={{ background: tag.color }}
          >
            {tag.name}
            <button
              onClick={() => handleRemove(tag.id)}
              disabled={loading === tag.id}
              className="rounded-full opacity-70 hover:opacity-100 disabled:opacity-40"
              aria-label={`Remover etiqueta ${tag.name}`}
            >
              <X className="size-2.5" />
            </button>
          </span>
        ))}
        <button
          onClick={() => setOpen((v) => !v)}
          className="inline-flex items-center gap-1 rounded-full border border-dashed border-zinc-300 px-2 py-0.5 text-[11px] text-zinc-400 hover:border-zinc-500 hover:text-zinc-600 dark:border-zinc-700 dark:hover:border-zinc-500"
        >
          <Plus className="size-2.5" /> Etiqueta
        </button>
      </div>

      {/* Dropdown */}
      {open && (
        <div className="absolute left-0 top-full z-20 mt-1 w-56 rounded-lg border border-zinc-200 bg-white shadow-lg dark:border-zinc-700 dark:bg-zinc-900">
          {available.length > 0 ? (
            <ul className="max-h-44 overflow-y-auto p-1">
              {available.map((tag) => (
                <li key={tag.id}>
                  <button
                    onClick={() => handleAdd(tag)}
                    disabled={loading === tag.id}
                    className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs hover:bg-zinc-100 disabled:opacity-50 dark:hover:bg-zinc-800"
                  >
                    <span
                      className="size-2.5 shrink-0 rounded-full"
                      style={{ background: tag.color }}
                    />
                    {tag.name}
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="px-3 py-2 text-xs text-zinc-400">
              {allTags.length === 0
                ? "Nenhuma etiqueta criada ainda."
                : "Todas as etiquetas já aplicadas."}
            </p>
          )}

          <div className="border-t border-zinc-100 p-1 dark:border-zinc-800">
            {!creating ? (
              <button
                onClick={() => setCreating(true)}
                className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-xs text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800"
              >
                <TagIcon className="size-3" /> Nova etiqueta…
              </button>
            ) : (
              <div className="space-y-1.5 p-1">
                <input
                  autoFocus
                  type="text"
                  placeholder="Nome da etiqueta"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleCreate()}
                  maxLength={50}
                  className="w-full rounded border border-zinc-200 px-2 py-1 text-xs outline-none focus:border-zinc-400 dark:border-zinc-700 dark:bg-zinc-800"
                />
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    value={newColor}
                    onChange={(e) => setNewColor(e.target.value)}
                    className="size-6 cursor-pointer rounded border-0 p-0"
                    title="Cor da etiqueta"
                  />
                  <button
                    onClick={handleCreate}
                    disabled={!newName.trim() || loading === "new"}
                    className="flex-1 rounded bg-zinc-900 px-2 py-1 text-xs font-medium text-white disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900"
                  >
                    {loading === "new" ? "…" : "Criar"}
                  </button>
                  <button
                    onClick={() => setCreating(false)}
                    className="text-xs text-zinc-400 hover:text-zinc-600"
                  >
                    <X className="size-3.5" />
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// LeadPanel
// ---------------------------------------------------------------------------

export function LeadPanel({
  lead: detail,
  allTags = [],
  currentTags = [],
}: {
  lead: LeadDetail | null;
  allTags?: Tag[];
  currentTags?: Tag[];
}) {
  const [copied, setCopied] = useState(false);

  if (!detail) {
    return (
      <div className="p-5 text-center">
        <div className="mx-auto mb-3 grid size-10 place-items-center rounded-full bg-zinc-100 text-zinc-400 dark:bg-zinc-900">
          <FileText className="size-5" />
        </div>
        <p className="text-sm font-medium">Sem lead ainda</p>
        <p className="mt-1 text-xs text-zinc-500">
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
  ];
  const shown = fields.filter(([, v]) => v);

  function copyBriefing() {
    if (!lead.briefing_md) return;
    navigator.clipboard.writeText(lead.briefing_md).then(() => {
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
          <p className="mt-0.5 text-xs text-zinc-500">{rota}</p>
        ) : null}
        <div className="mt-2 flex items-center justify-center gap-1.5">
          {lead.numero ? (
            <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] font-medium tabular-nums text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
              #{lead.numero}
            </span>
          ) : null}
          {lead.lead_temp ? <TempBadge temp={lead.lead_temp} /> : null}
        </div>
      </div>

      {/* Etiquetas */}
      <div className="border-t border-zinc-100 px-5 py-3 dark:border-zinc-800">
        <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-zinc-400">
          Etiquetas
        </p>
        <TagSelector
          phone={lead.phone}
          currentTags={currentTags}
          allTags={allTags}
        />
      </div>

      {shown.length > 0 ? (
        <div className="space-y-2.5 border-t border-zinc-100 px-5 py-4 dark:border-zinc-800">
          {shown.map(([label, value]) => (
            <div key={label} className="flex items-start justify-between gap-3">
              <span className="shrink-0 text-xs text-zinc-500">{label}</span>
              <span className="text-right text-xs font-medium">{value}</span>
            </div>
          ))}
        </div>
      ) : null}

      <div className="mt-auto space-y-2 border-t border-zinc-100 px-5 py-4 dark:border-zinc-800">
        <Link
          href={`/leads/${lead.numero}`}
          className="flex items-center justify-center gap-1.5 rounded-lg border border-zinc-300 px-3 py-2 text-sm font-medium hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-900"
        >
          <ExternalLink className="size-4" /> Ver lead completo
        </Link>
        {lead.briefing_md ? (
          <button
            onClick={copyBriefing}
            className="flex w-full items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-900"
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

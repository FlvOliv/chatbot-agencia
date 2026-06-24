"use client";

import { useState } from "react";
import Link from "next/link";

import { cn } from "@/lib/utils";
import { formatPhone } from "@/lib/format";
import type { ConversationSummary, Tag } from "@/lib/types";
import { Avatar } from "./avatar";
import { TempBadge } from "@/components/temp-badge";

type Tab = "todas" | "aguardando" | "quentes";

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const min = Math.floor(diff / 60000);
  if (min < 1) return "agora";
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h} h`;
  return `${Math.floor(h / 24)} d`;
}

const isHot = (c: ConversationSummary) =>
  c.lead_temp === "quente" || c.lead_temp === "urgente";

export function ConversationList({
  conversations,
  activePhone,
}: {
  conversations: ConversationSummary[];
  activePhone?: string;
}) {
  const [tab, setTab] = useState<Tab>("todas");
  const [filterTagId, setFilterTagId] = useState<string | null>(null);

  const waiting = conversations.filter((c) => c.bot_paused);
  const hot = conversations.filter(isHot);

  // Todas as tags únicas presentes nas conversas
  const allTagsMap = new Map<string, Tag>();
  for (const c of conversations) {
    for (const t of c.tags ?? []) {
      if (!allTagsMap.has(t.id)) allTagsMap.set(t.id, t);
    }
  }
  const uniqueTags = Array.from(allTagsMap.values()).sort((a, b) =>
    a.name.localeCompare(b.name),
  );

  const byTab =
    tab === "aguardando" ? waiting : tab === "quentes" ? hot : conversations;

  const list = filterTagId
    ? byTab.filter((c) => (c.tags ?? []).some((t) => t.id === filterTagId))
    : byTab;

  const tabs: Array<{ id: Tab; label: string; count: number }> = [
    { id: "todas", label: "Todas", count: conversations.length },
    { id: "aguardando", label: "Aguardando você", count: waiting.length },
    { id: "quentes", label: "Quentes", count: hot.length },
  ];

  return (
    <div>
      {/* Abas */}
      <div className="flex flex-wrap gap-1.5 border-b border-zinc-100 px-3 py-2 dark:border-zinc-800">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={cn(
              "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium transition-colors",
              tab === t.id
                ? "bg-zinc-900 text-zinc-50 dark:bg-zinc-100 dark:text-zinc-900"
                : "text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800",
            )}
          >
            {t.label}
            {t.count > 0 ? (
              <span
                className={cn(
                  "rounded-full px-1.5 text-[10px] tabular-nums",
                  tab === t.id
                    ? "bg-white/20"
                    : "bg-zinc-200 text-zinc-600 dark:bg-zinc-700 dark:text-zinc-300",
                )}
              >
                {t.count}
              </span>
            ) : null}
          </button>
        ))}
      </div>

      {/* Filtro por etiqueta — só aparece se houver etiquetas */}
      {uniqueTags.length > 0 && (
        <div className="flex gap-1.5 overflow-x-auto border-b border-zinc-100 px-3 py-2 dark:border-zinc-800">
          {filterTagId !== null && (
            <button
              onClick={() => setFilterTagId(null)}
              className="shrink-0 rounded-full border border-zinc-300 px-2 py-0.5 text-[10px] text-zinc-500 hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
            >
              ✕ limpar
            </button>
          )}
          {uniqueTags.map((tag) => (
            <button
              key={tag.id}
              onClick={() =>
                setFilterTagId((prev) => (prev === tag.id ? null : tag.id))
              }
              className={cn(
                "shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium text-white transition-opacity",
                filterTagId === tag.id ? "opacity-100 ring-2 ring-offset-1 ring-zinc-400" : "opacity-70 hover:opacity-100",
              )}
              style={{ background: tag.color }}
            >
              {tag.name}
            </button>
          ))}
        </div>
      )}

      {list.length === 0 ? (
        <div className="p-6 text-center text-sm text-zinc-500">
          {filterTagId
            ? "Nenhuma conversa com essa etiqueta."
            : tab === "aguardando"
              ? "Nenhuma conversa aguardando você."
              : tab === "quentes"
                ? "Nenhuma conversa quente agora."
                : "Nenhuma conversa ainda."}
        </div>
      ) : (
        <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
          {list.map((c) => {
            const name = c.customer_name?.trim() || formatPhone(c.phone);
            const active = c.phone === activePhone;
            return (
              <li key={c.phone}>
                <Link
                  href={`/conversas/${encodeURIComponent(c.phone)}`}
                  className={cn(
                    "flex items-center gap-3 px-3 py-3 transition-colors",
                    active
                      ? "border-l-2 border-zinc-900 bg-zinc-100 dark:border-zinc-100 dark:bg-zinc-900"
                      : "border-l-2 border-transparent hover:bg-zinc-50 dark:hover:bg-zinc-900/50",
                  )}
                >
                  <Avatar name={name} size={40} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-medium">{name}</span>
                      <span className="shrink-0 text-[11px] text-zinc-400">
                        {timeAgo(c.last_message_at)}
                      </span>
                    </div>
                    <p className="truncate text-xs text-zinc-500 dark:text-zinc-400">
                      {c.last_message_preview || "—"}
                    </p>
                    <div className="mt-1 flex items-center gap-1.5">
                      {c.bot_paused ? (
                        <span className="inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-800 dark:bg-amber-950 dark:text-amber-300">
                          Aguardando você
                        </span>
                      ) : null}
                      {c.lead_temp ? <TempBadge temp={c.lead_temp} /> : null}
                      {/* Mini-badges de etiqueta — só em telas lg+ */}
                      {(c.tags ?? []).length > 0 && (
                        <span className="hidden lg:flex items-center gap-1">
                          {(c.tags ?? []).slice(0, 3).map((tag) => (
                            <span
                              key={tag.id}
                              className="size-2 rounded-full"
                              style={{ background: tag.color }}
                              title={tag.name}
                            />
                          ))}
                          {(c.tags ?? []).length > 3 && (
                            <span className="text-[9px] text-zinc-400">
                              +{(c.tags ?? []).length - 3}
                            </span>
                          )}
                        </span>
                      )}
                    </div>
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

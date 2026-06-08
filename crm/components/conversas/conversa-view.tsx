"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Bot, Send, UserCheck, RotateCcw, AlertTriangle } from "lucide-react";

import { cn } from "@/lib/utils";
import type { ConversationDetail } from "@/lib/types";
import {
  releaseConversation,
  replyConversation,
  takeoverConversation,
} from "@/lib/actions";

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString("pt-BR", {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

export function ConversaView({
  conv,
  initialPaused,
}: {
  conv: ConversationDetail;
  initialPaused: boolean;
}) {
  const router = useRouter();
  const [paused, setPaused] = useState(initialPaused);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const title = conv.customer_name ?? conv.phone;

  function handleTakeover() {
    setError(null);
    startTransition(async () => {
      try {
        const r = await takeoverConversation(conv.phone);
        setPaused(r.bot_paused);
        router.refresh();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Erro ao assumir.");
      }
    });
  }

  function handleRelease() {
    setError(null);
    startTransition(async () => {
      try {
        const r = await releaseConversation(conv.phone);
        setPaused(r.bot_paused);
        router.refresh();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Erro ao devolver.");
      }
    });
  }

  function handleSend() {
    const body = text.trim();
    if (!body) return;
    setError(null);
    startTransition(async () => {
      try {
        const r = await replyConversation(conv.phone, body);
        setText("");
        setPaused(true);
        if (!r.sent) {
          setError(
            r.error ??
              "Mensagem registrada, mas não foi entregue (número ainda não configurado).",
          );
        }
        router.refresh();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Erro ao enviar.");
      }
    });
  }

  return (
    <div className="space-y-4">
      {/* Cabeçalho */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 p-4">
        <div className="min-w-0">
          <h1 className="text-lg font-semibold truncate">{title}</h1>
          <p className="text-xs text-zinc-500">{conv.phone}</p>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium",
              paused
                ? "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300"
                : "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
            )}
          >
            {paused ? (
              <>
                <UserCheck className="size-3.5" /> Você está atendendo
              </>
            ) : (
              <>
                <Bot className="size-3.5" /> Malu atendendo
              </>
            )}
          </span>
          {paused ? (
            <button
              onClick={handleRelease}
              disabled={pending}
              className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-300 dark:border-zinc-700 px-3 py-1.5 text-sm font-medium hover:bg-zinc-100 dark:hover:bg-zinc-900 disabled:opacity-50"
            >
              <RotateCcw className="size-4" /> Devolver pra Malu
            </button>
          ) : (
            <button
              onClick={handleTakeover}
              disabled={pending}
              className="inline-flex items-center gap-1.5 rounded-lg bg-zinc-900 text-zinc-50 dark:bg-zinc-100 dark:text-zinc-900 px-3 py-1.5 text-sm font-medium hover:opacity-90 disabled:opacity-50"
            >
              <UserCheck className="size-4" /> Assumir atendimento
            </button>
          )}
        </div>
      </div>

      {/* Thread */}
      <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 p-4 space-y-3 max-h-[55vh] overflow-y-auto">
        {conv.messages.length === 0 ? (
          <p className="text-sm text-zinc-500 text-center py-6">
            Sem mensagens nesta conversa.
          </p>
        ) : (
          conv.messages.map((m) => {
            const isClient = m.role === "user";
            const isHuman = m.model_used === "human";
            return (
              <div
                key={m.id}
                className={cn("flex", isClient ? "justify-start" : "justify-end")}
              >
                <div
                  className={cn(
                    "max-w-[78%] rounded-2xl px-3.5 py-2 text-sm whitespace-pre-wrap break-words",
                    isClient
                      ? "bg-zinc-100 dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100 rounded-bl-sm"
                      : isHuman
                        ? "bg-amber-500 text-white rounded-br-sm"
                        : "bg-emerald-600 text-white rounded-br-sm",
                  )}
                >
                  {!isClient ? (
                    <div className="mb-0.5 text-[10px] font-semibold uppercase tracking-wide opacity-80">
                      {isHuman ? "Você (Lu)" : "Malu"}
                    </div>
                  ) : null}
                  {m.content}
                  <div
                    className={cn(
                      "mt-0.5 text-[10px]",
                      isClient ? "text-zinc-400" : "text-white/70",
                    )}
                  >
                    {formatTime(m.created_at)}
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Erro */}
      {error ? (
        <div className="flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 dark:bg-amber-950/40 dark:border-amber-800 p-3 text-sm text-amber-800 dark:text-amber-300">
          <AlertTriangle className="size-4 shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      ) : null}

      {/* Caixa de resposta */}
      <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 p-3">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={
            paused
              ? "Escreva sua resposta para o cliente…"
              : "Escreva… (ao enviar, você assume o atendimento e a Malu pausa)"
          }
          rows={2}
          className="w-full resize-none bg-transparent text-sm outline-none placeholder:text-zinc-400"
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleSend();
          }}
        />
        <div className="flex items-center justify-between pt-2">
          <span className="text-[11px] text-zinc-400">
            Ctrl/⌘ + Enter para enviar
          </span>
          <button
            onClick={handleSend}
            disabled={pending || !text.trim()}
            className="inline-flex items-center gap-1.5 rounded-lg bg-zinc-900 text-zinc-50 dark:bg-zinc-100 dark:text-zinc-900 px-4 py-2 text-sm font-medium hover:opacity-90 disabled:opacity-40"
          >
            <Send className="size-4" /> Enviar
          </button>
        </div>
      </div>
    </div>
  );
}

"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import {
  Bot,
  Send,
  UserCheck,
  RotateCcw,
  AlertTriangle,
  PanelRightClose,
  PanelRightOpen,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { formatPhone } from "@/lib/format";
import type { ConversationDetail } from "@/lib/types";
import { AudioMessage } from "./audio-message";
import { AudioRecorder } from "./audio-recorder";
import {
  releaseConversation,
  replyConversation,
  takeoverConversation,
} from "@/lib/actions";
import { Avatar } from "./avatar";

const QUICK_REPLIES: Array<{ label: string; text: string }> = [
  {
    label: "Já te retorno",
    text: "Oi! Já recebi suas informações 💛 Vou verificar as melhores opções e já te retorno.",
  },
  { label: "Pedir datas", text: "Pode me confirmar as datas de ida e volta?" },
  {
    label: "Quantas pessoas",
    text: "Quantas pessoas vão viajar? (adultos e crianças)",
  },
  {
    label: "Preparando cotação",
    text: "Estou preparando sua cotação e te mando aqui assim que ficar pronta!",
  },
  {
    label: "Instagram",
    text: "Me segue no Instagram pra ver as novidades: instagram.com/lumilhaseviagens",
  },
];

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

function dayKey(iso: string): string {
  return new Date(iso).toDateString();
}

function dayLabel(iso: string): string {
  const d = new Date(iso);
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  if (d.toDateString() === today.toDateString()) return "Hoje";
  if (d.toDateString() === yesterday.toDateString()) return "Ontem";
  return d.toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "long",
  });
}

export function ConversaView({
  conv,
  initialPaused,
  onToggleLead,
  leadOpen,
}: {
  conv: ConversationDetail;
  initialPaused: boolean;
  onToggleLead?: () => void;
  leadOpen?: boolean;
}) {
  const router = useRouter();
  const [paused, setPaused] = useState(initialPaused);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const name = conv.customer_name?.trim() || formatPhone(conv.phone);

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

  let lastDay = "";

  return (
    <div className="flex h-full flex-col">
      {/* Cabeçalho */}
      <div className="flex items-center gap-3 border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
        <Avatar name={name} size={36} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold">{name}</p>
          <p
            className={cn(
              "flex items-center gap-1 text-xs",
              paused ? "text-amber-600 dark:text-amber-400" : "text-emerald-600 dark:text-emerald-400",
            )}
          >
            {paused ? (
              <>
                <UserCheck className="size-3" /> Você está atendendo
              </>
            ) : (
              <>
                <Bot className="size-3" /> Malu atendendo
              </>
            )}
          </p>
        </div>
        {paused ? (
          <button
            onClick={handleRelease}
            disabled={pending}
            className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-300 px-3 py-1.5 text-sm font-medium hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-900"
          >
            <RotateCcw className="size-4" /> Devolver
          </button>
        ) : (
          <button
            onClick={handleTakeover}
            disabled={pending}
            className="inline-flex items-center gap-1.5 rounded-lg bg-zinc-900 px-3 py-1.5 text-sm font-medium text-zinc-50 hover:opacity-90 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
          >
            <UserCheck className="size-4" /> Assumir
          </button>
        )}
        {onToggleLead ? (
          <button
            onClick={onToggleLead}
            aria-label={leadOpen ? "Esconder detalhes do lead" : "Mostrar detalhes do lead"}
            title={leadOpen ? "Esconder detalhes" : "Mostrar detalhes"}
            className="hidden size-9 shrink-0 place-items-center rounded-lg text-zinc-500 hover:bg-zinc-100 lg:grid dark:hover:bg-zinc-800"
          >
            {leadOpen ? (
              <PanelRightClose className="size-5" />
            ) : (
              <PanelRightOpen className="size-5" />
            )}
          </button>
        ) : null}
      </div>

      {/* Thread */}
      <div className="flex-1 space-y-2 overflow-y-auto bg-zinc-50 px-4 py-4 dark:bg-zinc-900/40">
        {conv.messages.length === 0 ? (
          <p className="py-6 text-center text-sm text-zinc-500">
            Sem mensagens nesta conversa.
          </p>
        ) : (
          conv.messages.map((m) => {
            const isClient = m.role === "user";
            const isHuman = m.model_used === "human";
            const dk = dayKey(m.created_at);
            const showDay = dk !== lastDay;
            lastDay = dk;
            return (
              <div key={m.id}>
                {showDay ? (
                  <div className="my-3 text-center">
                    <span className="rounded-full bg-white px-2.5 py-0.5 text-[11px] text-zinc-500 shadow-sm dark:bg-zinc-800">
                      {dayLabel(m.created_at)}
                    </span>
                  </div>
                ) : null}
                <div className={cn("flex", isClient ? "justify-start" : "justify-end")}>
                  <div
                    className={cn(
                      "max-w-[80%] whitespace-pre-wrap break-words rounded-2xl px-3.5 py-2 text-sm",
                      isClient
                        ? "rounded-bl-sm bg-white text-zinc-900 shadow-sm dark:bg-zinc-800 dark:text-zinc-100"
                        : isHuman
                          ? "rounded-br-sm bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
                          : "rounded-br-sm bg-emerald-600 text-white",
                    )}
                  >
                    {!isClient ? (
                      <div className="mb-0.5 text-[10px] font-semibold uppercase tracking-wide opacity-80">
                        {isHuman ? "Você (Lu)" : "Malu"}
                      </div>
                    ) : null}
                    {m.content}
                    {m.audio_url ? <AudioMessage src={m.audio_url} /> : null}
                    <div
                      className={cn(
                        "mt-0.5 text-[10px]",
                        isClient ? "text-zinc-400" : "text-white/70 dark:text-current dark:opacity-60",
                      )}
                    >
                      {formatTime(m.created_at)}
                    </div>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Erro */}
      {error ? (
        <div className="flex items-start gap-2 border-t border-amber-200 bg-amber-50 px-4 py-2.5 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
          <span>{error}</span>
        </div>
      ) : null}

      {/* Compositor */}
      <div className="border-t border-zinc-200 p-3 dark:border-zinc-800">
        <div className="mb-2 flex gap-1.5 overflow-x-auto pb-0.5">
          {QUICK_REPLIES.map((r) => (
            <button
              key={r.label}
              type="button"
              onClick={() => setText(r.text)}
              title={r.text}
              className="shrink-0 rounded-full border border-zinc-200 px-3 py-1 text-xs text-zinc-600 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
            >
              {r.label}
            </button>
          ))}
        </div>
        <div className="flex items-end gap-2">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={
              paused
                ? "Escreva sua resposta…"
                : "Escreva… (ao enviar, você assume e a Malu pausa)"
            }
            rows={1}
            className="max-h-32 min-h-[40px] flex-1 resize-none rounded-xl border border-zinc-200 bg-white px-3 py-2 text-sm outline-none placeholder:text-zinc-400 focus:border-zinc-400 dark:border-zinc-800 dark:bg-zinc-950 dark:focus:border-zinc-600"
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleSend();
            }}
          />
          <AudioRecorder
            phone={conv.phone}
            onSent={() => {
              setPaused(true);
              router.refresh();
            }}
            onError={setError}
          />
          <button
            onClick={handleSend}
            disabled={pending || !text.trim()}
            aria-label="Enviar"
            className="grid size-10 shrink-0 place-items-center rounded-xl bg-zinc-900 text-zinc-50 hover:opacity-90 disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900"
          >
            <Send className="size-4" />
          </button>
        </div>
        <p className="mt-1.5 text-[11px] text-zinc-400">
          Ctrl/⌘ + Enter para enviar · 🎤 grava nota de voz
        </p>
      </div>
    </div>
  );
}

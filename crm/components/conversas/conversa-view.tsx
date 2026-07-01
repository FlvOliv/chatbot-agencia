"use client";

import { useState, useTransition, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  Bot,
  Send,
  UserCheck,
  RotateCcw,
  AlertTriangle,
  PanelRightClose,
  PanelRightOpen,
  Trash2,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { formatPhone } from "@/lib/format";
import type { ConversationDetail, Tag } from "@/lib/types";
import { AudioMessage } from "./audio-message";
import { AudioRecorder } from "./audio-recorder";
import { TagSelector } from "./tag-selector";
import {
  deleteConversation,
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
  allTags = [],
  currentTags = [],
}: {
  conv: ConversationDetail;
  initialPaused: boolean;
  onToggleLead?: () => void;
  leadOpen?: boolean;
  allTags?: Tag[];
  currentTags?: Tag[];
}) {
  const router = useRouter();
  const [paused, setPaused] = useState(initialPaused);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [recording, setRecording] = useState(false);
  const [pending, startTransition] = useTransition();
  const [messages, setMessages] = useState(conv.messages);

  const name = conv.customer_name?.trim() || formatPhone(conv.phone);

  // Thread "ao vivo" sem recarregar a página: as mensagens ficam em estado e são
  // atualizadas por um poll LEVE (~4s) só desta conversa (sidebar/lead seguem no
  // refresh lento da página). Erro de rede mantém o que está na tela.
  const refreshMessages = useCallback(async () => {
    try {
      const res = await fetch(
        `/api/panel/conversation/${encodeURIComponent(conv.phone)}`,
        { cache: "no-store" },
      );
      if (!res.ok) return;
      const data = await res.json();
      // Só atualiza com lista não-vazia — evita apagar a thread por um glitch.
      if (Array.isArray(data?.messages) && data.messages.length > 0)
        setMessages(data.messages);
    } catch {
      // mantém as mensagens atuais (sem piscar)
    }
  }, [conv.phone]);

  // Trocar de conversa reinicia a thread com o que veio do servidor (SSR).
  useEffect(() => {
    setMessages(conv.messages);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conv.phone]);

  // Poll só da thread, quando a aba está visível.
  useEffect(() => {
    const id = setInterval(() => {
      if (document.visibilityState === "visible") refreshMessages();
    }, 4000);
    return () => clearInterval(id);
  }, [refreshMessages]);

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
        refreshMessages();
        router.refresh();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Erro ao enviar.");
      }
    });
  }

  function handleDelete() {
    if (
      !window.confirm(
        `Excluir a conversa com ${name}? As mensagens somem do painel e a Malu trata a próxima mensagem como NOVA. Não afeta leads. Ação irreversível.`,
      )
    )
      return;
    setError(null);
    startTransition(async () => {
      try {
        await deleteConversation(conv.phone);
        router.push("/conversas");
      } catch (e) {
        setError(e instanceof Error ? e.message : "Erro ao excluir.");
      }
    });
  }

  let lastDay = "";

  return (
    <div className="flex h-full flex-col">
      {/* Cabeçalho */}
      <div className="flex items-center gap-3 border-b border-border px-4 py-3">
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
            className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-sm font-medium hover:bg-accent disabled:opacity-50"
          >
            <RotateCcw className="size-4" /> Devolver
          </button>
        ) : (
          <button
            onClick={handleTakeover}
            disabled={pending}
            className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
          >
            <UserCheck className="size-4" /> Assumir
          </button>
        )}
        <button
          onClick={handleDelete}
          disabled={pending}
          aria-label="Excluir conversa"
          title="Excluir conversa (faxina de teste — não afeta leads)"
          className="grid size-9 shrink-0 place-items-center rounded-lg text-muted-foreground/70 hover:bg-red-50 hover:text-red-600 disabled:opacity-50 dark:hover:bg-red-950/40"
        >
          <Trash2 className="size-4" />
        </button>
        {onToggleLead ? (
          <button
            onClick={onToggleLead}
            aria-label={leadOpen ? "Esconder detalhes do lead" : "Mostrar detalhes do lead"}
            title={leadOpen ? "Esconder detalhes" : "Mostrar detalhes"}
            className="hidden size-9 shrink-0 place-items-center rounded-lg text-muted-foreground hover:bg-accent lg:grid"
          >
            {leadOpen ? (
              <PanelRightClose className="size-5" />
            ) : (
              <PanelRightOpen className="size-5" />
            )}
          </button>
        ) : null}
      </div>

      {/* Etiquetas (sempre visível, independe de ter lead) */}
      <div className="flex items-center gap-2 border-b border-border px-4 py-2">
        <TagSelector
          key={conv.phone}
          phone={conv.phone}
          currentTags={currentTags}
          allTags={allTags}
        />
      </div>

      {/* Thread */}
      <div className="flex-1 space-y-2 overflow-y-auto overscroll-contain bg-muted/60 px-4 py-4 [-webkit-overflow-scrolling:touch]">
        {messages.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            Sem mensagens nesta conversa.
          </p>
        ) : (
          messages.map((m) => {
            const isClient = m.role === "user";
            const isHuman = m.model_used === "human";
            const dk = dayKey(m.created_at);
            const showDay = dk !== lastDay;
            lastDay = dk;
            return (
              <div key={m.id}>
                {showDay ? (
                  <div className="my-3 text-center">
                    <span className="rounded-full bg-card px-2.5 py-0.5 text-[11px] text-muted-foreground shadow-sm">
                      {dayLabel(m.created_at)}
                    </span>
                  </div>
                ) : null}
                <div className={cn("flex", isClient ? "justify-start" : "justify-end")}>
                  <div
                    className={cn(
                      "max-w-[80%] whitespace-pre-wrap break-words rounded-2xl px-3.5 py-2 text-sm",
                      isClient
                        ? "rounded-bl-sm bg-card text-card-foreground shadow-sm"
                        : isHuman
                          ? "rounded-br-sm bg-gold text-gold-foreground"
                          : "rounded-br-sm bg-primary text-primary-foreground",
                    )}
                  >
                    {!isClient ? (
                      <div className="mb-0.5 text-[10px] font-semibold uppercase tracking-wide opacity-80">
                        {isHuman ? "Você (Lu)" : "Malu"}
                      </div>
                    ) : null}
                    {m.audio_url && m.content === "🎤 Áudio" ? null : m.content}
                    {m.audio_url ? <AudioMessage src={m.audio_url} /> : null}
                    <div
                      className={cn(
                        "mt-0.5 text-[10px]",
                        isClient ? "text-muted-foreground" : "opacity-70",
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
      <div className="border-t border-border p-3">
        {!recording ? (
          <div className="mb-2 flex gap-1.5 overflow-x-auto pb-0.5">
            {QUICK_REPLIES.map((r) => (
              <button
                key={r.label}
                type="button"
                onClick={() => setText(r.text)}
                title={r.text}
                className="shrink-0 rounded-full border border-border px-3 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              >
                {r.label}
              </button>
            ))}
          </div>
        ) : null}
        <div className="flex items-end gap-2">
          {!recording ? (
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={
                paused
                  ? "Escreva sua resposta…"
                  : "Escreva… (ao enviar, você assume e a Malu pausa)"
              }
              rows={1}
              className="max-h-32 min-h-[40px] flex-1 resize-none rounded-xl border border-input bg-card px-3 py-2 text-base sm:text-sm outline-none placeholder:text-muted-foreground/70 focus:border-ring"
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleSend();
              }}
            />
          ) : null}
          <AudioRecorder
            phone={conv.phone}
            onSent={() => {
              setPaused(true);
              refreshMessages();
              router.refresh();
            }}
            onError={setError}
            onRecordingChange={setRecording}
          />
          {!recording ? (
            <button
              onClick={handleSend}
              disabled={pending || !text.trim()}
              aria-label="Enviar"
              className="grid size-10 shrink-0 place-items-center rounded-xl bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-40"
            >
              <Send className="size-4" />
            </button>
          ) : null}
        </div>
        {!recording ? (
          <p className="mt-1.5 text-[11px] text-muted-foreground/80">
            Ctrl/⌘ + Enter para enviar · 🎤 grava nota de voz
          </p>
        ) : null}
      </div>
    </div>
  );
}

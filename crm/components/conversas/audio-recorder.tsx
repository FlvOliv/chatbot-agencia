"use client";

import { useRef, useState } from "react";
import { Mic, Send, Trash2, Loader2 } from "lucide-react";

import { replyAudioConversation } from "@/lib/actions";

/** Escolhe o melhor mimeType suportado (Chrome=webm, Safari/iOS=mp4). */
function pickMime(): string {
  if (typeof MediaRecorder === "undefined") return "";
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
    "audio/ogg",
  ];
  for (const c of candidates) {
    if (MediaRecorder.isTypeSupported(c)) return c;
  }
  return "";
}

function fmt(s: number): string {
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${r.toString().padStart(2, "0")}`;
}

type State = "idle" | "recording" | "sending";

export function AudioRecorder({
  phone,
  onSent,
  onError,
  onRecordingChange,
}: {
  phone: string;
  onSent: () => void;
  onError?: (msg: string | null) => void;
  onRecordingChange?: (recording: boolean) => void;
}) {
  const [state, setState] = useState<State>("idle");
  const [seconds, setSeconds] = useState(0);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const cancelledRef = useRef(false);

  function stopTimer() {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }

  function finish() {
    setState("idle");
    setSeconds(0);
    onRecordingChange?.(false);
  }

  async function start() {
    onError?.(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = pickMime();
      const mr = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      chunksRef.current = [];
      cancelledRef.current = false;

      mr.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        stopTimer();

        if (cancelledRef.current) {
          finish();
          return;
        }

        const type = mr.mimeType || "audio/webm";
        const blob = new Blob(chunksRef.current, { type });
        if (blob.size === 0) {
          finish();
          return;
        }

        setState("sending");
        try {
          const ext = type.includes("mp4")
            ? "mp4"
            : type.includes("ogg")
              ? "ogg"
              : "webm";
          const fd = new FormData();
          fd.append("audio", blob, `nota.${ext}`);
          const r = await replyAudioConversation(phone, fd);
          if (!r.sent) {
            onError?.(
              r.error ?? "Áudio registrado, mas não foi entregue ao cliente.",
            );
          }
          onSent();
        } catch (e) {
          onError?.(e instanceof Error ? e.message : "Erro ao enviar o áudio.");
        } finally {
          finish();
        }
      };

      mr.start();
      recorderRef.current = mr;
      setState("recording");
      setSeconds(0);
      onRecordingChange?.(true);
      timerRef.current = setInterval(() => setSeconds((s) => s + 1), 1000);
    } catch {
      onError?.(
        "Não consegui acessar o microfone. Permita o acesso no navegador.",
      );
    }
  }

  function stopAndSend() {
    cancelledRef.current = false;
    recorderRef.current?.stop();
  }

  function cancel() {
    cancelledRef.current = true;
    recorderRef.current?.stop();
  }

  // Gravando OU enviando → barra larga (a ConversaView esconde o textarea).
  if (state === "recording" || state === "sending") {
    const sending = state === "sending";
    return (
      <div className="flex h-10 flex-1 items-center gap-3 rounded-xl border border-red-200 bg-red-50/60 px-3 dark:border-red-900/60 dark:bg-red-950/30">
        <button
          onClick={cancel}
          disabled={sending}
          aria-label="Cancelar gravação"
          title="Cancelar"
          className="grid size-7 shrink-0 place-items-center rounded-full text-zinc-500 hover:bg-zinc-200/60 disabled:opacity-40 dark:hover:bg-zinc-800"
        >
          <Trash2 className="size-4" />
        </button>

        <span className="flex items-center gap-2 text-sm font-medium tabular-nums text-red-600 dark:text-red-400">
          <span className="size-2 animate-pulse rounded-full bg-red-500" />
          {fmt(seconds)}
        </span>

        <span className="flex-1 truncate text-xs text-zinc-400">
          {sending ? "Enviando…" : "Gravando — toque no avião para enviar"}
        </span>

        <button
          onClick={stopAndSend}
          disabled={sending}
          aria-label="Enviar áudio"
          title="Enviar"
          className="grid size-8 shrink-0 place-items-center rounded-full bg-zinc-900 text-white hover:opacity-90 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
        >
          {sending ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <Send className="size-4" />
          )}
        </button>
      </div>
    );
  }

  return (
    <button
      onClick={start}
      aria-label="Gravar áudio"
      title="Gravar nota de voz"
      className="grid size-10 shrink-0 place-items-center rounded-xl text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800"
    >
      <Mic className="size-5" />
    </button>
  );
}

"use client";

import { useRef, useState } from "react";
import { Mic, Square, X, Loader2 } from "lucide-react";

import { replyAudioConversation } from "@/lib/actions";

/** Escolhe o melhor mimeType suportado pelo navegador (Chrome=webm, Safari=mp4). */
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
}: {
  phone: string;
  onSent: () => void;
  onError?: (msg: string | null) => void;
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
          setState("idle");
          setSeconds(0);
          return;
        }

        const type = mr.mimeType || "audio/webm";
        const blob = new Blob(chunksRef.current, { type });
        if (blob.size === 0) {
          setState("idle");
          setSeconds(0);
          return;
        }

        setState("sending");
        try {
          const ext = type.includes("mp4") ? "mp4" : type.includes("ogg") ? "ogg" : "webm";
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
          setState("idle");
          setSeconds(0);
        }
      };

      mr.start();
      recorderRef.current = mr;
      setState("recording");
      setSeconds(0);
      timerRef.current = setInterval(() => setSeconds((s) => s + 1), 1000);
    } catch {
      onError?.(
        "Não consegui acessar o microfone. Permita o acesso no navegador.",
      );
    }
  }

  function stop() {
    cancelledRef.current = false;
    recorderRef.current?.stop();
  }

  function cancel() {
    cancelledRef.current = true;
    recorderRef.current?.stop();
  }

  if (state === "sending") {
    return (
      <div
        className="grid size-10 shrink-0 place-items-center rounded-xl text-zinc-400"
        aria-label="Enviando áudio"
      >
        <Loader2 className="size-4 animate-spin" />
      </div>
    );
  }

  if (state === "recording") {
    return (
      <div className="flex shrink-0 items-center gap-1.5">
        <button
          onClick={cancel}
          aria-label="Cancelar gravação"
          title="Cancelar"
          className="grid size-10 place-items-center rounded-xl text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800"
        >
          <X className="size-4" />
        </button>
        <span className="min-w-[44px] text-center text-xs font-medium tabular-nums text-red-500">
          ● {fmt(seconds)}
        </span>
        <button
          onClick={stop}
          aria-label="Parar e enviar áudio"
          title="Parar e enviar"
          className="grid size-10 place-items-center rounded-xl bg-red-500 text-white hover:opacity-90"
        >
          <Square className="size-4 fill-current" />
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

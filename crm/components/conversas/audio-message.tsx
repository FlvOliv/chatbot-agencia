"use client";

import { useEffect, useRef, useState } from "react";
import { Play, Pause } from "lucide-react";

/**
 * Player de áudio estilo WhatsApp — clique no play e toca, sem menu de 3 pontos.
 *
 * Usa um <audio> escondido + controles próprios (play/pause, barra clicável,
 * tempo). As cores herdam a bolha (`currentColor`), então funciona tanto na
 * bolha clara do cliente quanto na escura da Lu.
 *
 * IMPORTANTE: o painel se atualiza sozinho a cada 6s (`AutoRefresh`), e a cada
 * vez o backend gera um link assinado NOVO. Por isso CONGELAMOS a URL no 1º
 * render (`useState(src)` sem setter) — o src nunca muda e a reprodução não trava.
 */
function fmt(s: number): string {
  if (!isFinite(s) || s < 0) s = 0;
  const m = Math.floor(s / 60);
  const r = Math.floor(s % 60);
  return `${m}:${r.toString().padStart(2, "0")}`;
}

export function AudioMessage({ src }: { src: string }) {
  const [frozenSrc] = useState(src);
  const audioRef = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(0);

  useEffect(() => {
    const a = audioRef.current;
    if (!a) return;
    const onTime = () => setCurrent(a.currentTime);
    const onLoaded = () => setDuration(a.duration || 0);
    const onEnd = () => {
      setPlaying(false);
      setCurrent(0);
    };
    a.addEventListener("timeupdate", onTime);
    a.addEventListener("loadedmetadata", onLoaded);
    a.addEventListener("durationchange", onLoaded);
    a.addEventListener("ended", onEnd);
    a.addEventListener("pause", () => setPlaying(false));
    a.addEventListener("play", () => setPlaying(true));
    return () => {
      a.removeEventListener("timeupdate", onTime);
      a.removeEventListener("loadedmetadata", onLoaded);
      a.removeEventListener("durationchange", onLoaded);
      a.removeEventListener("ended", onEnd);
    };
  }, []);

  function toggle() {
    const a = audioRef.current;
    if (!a) return;
    if (a.paused) a.play();
    else a.pause();
  }

  function seek(e: React.MouseEvent<HTMLDivElement>) {
    const a = audioRef.current;
    if (!a || !duration) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const pct = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
    a.currentTime = pct * duration;
    setCurrent(a.currentTime);
  }

  const pct = duration ? (current / duration) * 100 : 0;
  const timeLabel = playing || current > 0 ? current : duration;

  return (
    <div className="mt-1 flex min-w-[200px] max-w-[260px] items-center gap-2.5">
      <audio ref={audioRef} src={frozenSrc} preload="metadata" className="hidden" />
      <button
        onClick={toggle}
        aria-label={playing ? "Pausar" : "Reproduzir"}
        className="grid size-9 shrink-0 place-items-center rounded-full bg-current/15 transition-colors hover:bg-current/25"
      >
        {playing ? (
          <Pause className="size-4 fill-current" />
        ) : (
          <Play className="size-4 translate-x-px fill-current" />
        )}
      </button>
      <div className="flex-1">
        <div
          onClick={seek}
          className="group flex h-5 cursor-pointer items-center"
        >
          <div className="relative h-1 w-full rounded-full bg-current/25">
            <div
              className="absolute inset-y-0 left-0 rounded-full bg-current/80"
              style={{ width: `${pct}%` }}
            />
            <div
              className="absolute top-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-current opacity-0 transition-opacity group-hover:opacity-100"
              style={{ left: `${pct}%` }}
            />
          </div>
        </div>
        <div className="mt-0.5 text-[10px] tabular-nums opacity-60">
          {fmt(timeLabel)}
        </div>
      </div>
    </div>
  );
}

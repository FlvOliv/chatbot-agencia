"use client";

import { useRef } from "react";

/**
 * Player de áudio das notas de voz do WhatsApp.
 *
 * As notas de voz vêm em Opus/OGG SEM a duração no cabeçalho, então o Chrome
 * mostra "0:00" e para a reprodução cedo (acha que o áudio tem duração zero).
 * Truque conhecido: ao carregar os metadados, se a duração vier inválida
 * (Infinity/NaN/0), forçamos um seek pro fim — o navegador busca o final do
 * arquivo (range request) e recalcula a duração real; depois voltamos pro 0.
 * O servidor (Supabase Storage) suporta range (`accept-ranges: bytes`), então
 * o seek funciona e a faixa toca inteira + fica navegável.
 */
export function AudioMessage({ src }: { src: string }) {
  const ref = useRef<HTMLAudioElement>(null);

  function fixDuration() {
    const a = ref.current;
    if (!a) return;
    if (a.duration === Infinity || Number.isNaN(a.duration) || a.duration === 0) {
      const onTimeUpdate = () => {
        a.removeEventListener("timeupdate", onTimeUpdate);
        // Volta pro início depois que a duração real foi descoberta.
        a.currentTime = 0;
      };
      a.addEventListener("timeupdate", onTimeUpdate);
      // Seek pra um ponto absurdamente longe → navegador vai até o fim do arquivo.
      a.currentTime = 1e101;
    }
  }

  return (
    <audio
      ref={ref}
      controls
      preload="metadata"
      src={src}
      onLoadedMetadata={fixDuration}
      className="mt-1 w-full max-w-[260px]"
    />
  );
}

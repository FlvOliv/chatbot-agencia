"use client";

import { useState } from "react";

/**
 * Player das notas de voz dos clientes.
 *
 * IMPORTANTE: o painel se atualiza sozinho a cada 8s (`AutoRefresh` →
 * `router.refresh()`), e a cada atualização o backend gera um link assinado
 * NOVO pro áudio. Se o `<audio src>` mudasse, o navegador recarregaria o player
 * e a reprodução travaria no meio. Por isso CONGELAMOS a URL no primeiro render
 * (`useState(src)` sem setter): o `src` nunca muda, o player não recarrega e
 * toca até o fim. A URL inicial é válida por ~1h (AUDIO_URL_TTL) — de sobra.
 *
 * O áudio é recodificado pra MP3 no servidor (ffmpeg) antes de guardar, então a
 * duração e a navegação funcionam normalmente.
 */
export function AudioMessage({ src }: { src: string }) {
  const [frozenSrc] = useState(src);
  return (
    <audio
      controls
      preload="metadata"
      src={frozenSrc}
      className="mt-1 w-full max-w-[260px]"
    />
  );
}

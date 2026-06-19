"use client";

/**
 * Player das notas de voz dos clientes.
 *
 * O áudio é recodificado pra MP3 no servidor (ffmpeg) antes de ser guardado —
 * isso conserta a duração quebrada do Opus/OGG do WhatsApp, que fazia o player
 * parar cedo. Com MP3, um <audio> simples toca inteiro e mostra a duração.
 */
export function AudioMessage({ src }: { src: string }) {
  return (
    <audio
      controls
      preload="metadata"
      src={src}
      className="mt-1 w-full max-w-[260px]"
    />
  );
}

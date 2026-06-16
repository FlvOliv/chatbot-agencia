"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/**
 * Atualiza a tela sozinha em intervalos (painel "ao vivo"), sem F5.
 *
 * Chama router.refresh(), que re-renderiza os server components com dados
 * frescos do backend — a chave da API continua no servidor, e o estado dos
 * client components (ex.: o texto que a Lu está digitando) é preservado.
 */
export function AutoRefresh({ intervalMs = 8000 }: { intervalMs?: number }) {
  const router = useRouter();

  useEffect(() => {
    const id = setInterval(() => {
      // Não atualiza com a aba em segundo plano (economiza requisições)
      if (document.visibilityState === "visible") {
        router.refresh();
      }
    }, intervalMs);
    return () => clearInterval(id);
  }, [router, intervalMs]);

  return null;
}

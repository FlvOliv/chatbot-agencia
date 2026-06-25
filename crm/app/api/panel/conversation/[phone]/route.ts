import { NextResponse } from "next/server";

import { getConversation } from "@/lib/api";

/**
 * Endpoint interno do painel pra POLL leve da thread (client-side). A chave da
 * API continua no servidor (apiFetch). Protegido pelo middleware de sessão.
 */
export async function GET(
  _req: Request,
  { params }: { params: Promise<{ phone: string }> },
) {
  const { phone } = await params;
  const conv = await getConversation(decodeURIComponent(phone), 200);
  // Em falha (backend fora/transitório), devolve erro → o cliente IGNORA e mantém
  // o que já está na tela (não pisca/apaga a thread).
  if (!conv) {
    return NextResponse.json({ error: "indisponível" }, { status: 502 });
  }
  return NextResponse.json(conv, { headers: { "Cache-Control": "no-store" } });
}

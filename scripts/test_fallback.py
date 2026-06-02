"""Teste end-to-end do fallback Gemini → Groq.

Dispara 6 requests em sequência rápida (Gemini 2.5 Flash free tier é 5 RPM).
A 6ª chamada deve estourar a quota e o `route_and_ask` deve fazer fallback
automático pro Groq se `AI_FALLBACK` estiver configurado como `auto` ou `groq`.

Uso:
    .venv/bin/python scripts/test_fallback.py

Pré-requisitos no .env:
    AI_PRIMARY=gemini
    AI_FALLBACK=auto       (ou: groq)
    GEMINI_API_KEY=...     (preenchido)
    GROQ_API_KEY=...       (preenchido — sem ele o fallback não tem pra onde ir)
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ai import route_and_ask  # noqa: E402
from app.config import settings  # noqa: E402

LINHA = "═" * 70


def cabecalho() -> None:
    print("\n" + LINHA)
    print("  TESTE DE FALLBACK Gemini → Groq")
    print(LINHA)
    print(f"  AI_PRIMARY      = {settings.ai_primary}")
    print(f"  AI_FALLBACK     = {settings.ai_fallback}")
    print(f"  GEMINI_MODEL    = {settings.gemini_model}")
    print(f"  GROQ_MODEL      = {settings.groq_model}")
    print(f"  GEMINI_API_KEY  = {'***configurada***' if settings.gemini_api_key else 'VAZIA'}")
    print(f"  GROQ_API_KEY    = {'***configurada***' if settings.groq_api_key else 'VAZIA'}")
    print(LINHA + "\n")


def validar_setup() -> bool:
    erros = []
    if settings.ai_primary != "gemini":
        erros.append(f"AI_PRIMARY deveria ser 'gemini', está '{settings.ai_primary}'")
    if settings.ai_fallback not in ("auto", "groq"):
        erros.append(
            f"AI_FALLBACK deveria ser 'auto' ou 'groq' (está '{settings.ai_fallback}') — "
            f"sem isso o fallback NÃO acontece. Edite o .env e rode de novo."
        )
    if not settings.gemini_api_key:
        erros.append("GEMINI_API_KEY vazia no .env")
    if not settings.groq_api_key:
        erros.append("GROQ_API_KEY vazia no .env (sem ela não há pra onde fazer fallback)")
    if erros:
        print("⚠️  Pré-requisitos não atendidos:")
        for e in erros:
            print(f"   - {e}")
        return False
    return True


async def run() -> None:
    cabecalho()
    if not validar_setup():
        sys.exit(1)

    # Cada turno usa uma pergunta curta — economiza tokens mas conta 1 request
    perguntas = [
        "Diga apenas: oi",
        "Diga apenas: tudo bem",
        "Diga apenas: ok",
        "Diga apenas: sim",
        "Diga apenas: certo",
        "Diga apenas: pronto",
    ]

    contagem_modelos: dict[str, int] = {}
    fallback_acionado = False

    for i, pergunta in enumerate(perguntas, 1):
        t0 = time.time()
        try:
            text, model = await route_and_ask(
                [{"role": "user", "content": pergunta}]
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  TURNO {i}  | EXCEPTION: {type(exc).__name__}: {exc}")
            continue
        elapsed_ms = int((time.time() - t0) * 1000)
        contagem_modelos[model] = contagem_modelos.get(model, 0) + 1
        if "llama" in model.lower() and not fallback_acionado:
            fallback_acionado = True
            print(f"  TURNO {i}  | ✅ FALLBACK ACIONADO — Groq assumiu")
        marca = "🔵" if "gemini" in model.lower() else "🟢" if "llama" in model.lower() else "❌"
        snippet = (text or "")[:60].replace("\n", " ")
        print(f"  TURNO {i}  | {marca} {model:30s} | {elapsed_ms:5d}ms | {snippet!r}")

    print()
    print(LINHA)
    print("  RESUMO")
    print(LINHA)
    for modelo, count in sorted(contagem_modelos.items(), key=lambda x: -x[1]):
        print(f"  {modelo:30s} → {count} respostas")
    print()
    if fallback_acionado:
        print("  ✅ FALLBACK FUNCIONOU — Groq assumiu quando Gemini estourou quota")
    elif "error" in contagem_modelos:
        print("  ❌ FALLBACK NÃO ACIONOU — alguma chamada retornou 'error'")
        print("     Verifique GROQ_API_KEY no .env e AI_FALLBACK=auto ou groq")
    else:
        print("  🟡 GEMINI NÃO ESTOUROU — sua quota ainda não bateu o limite")
        print("     Rode de novo em ~1 min pra forçar (ou ajuste o limite no Google AI Studio)")
    print()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\nencerrado")

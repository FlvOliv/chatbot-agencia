"""Demonstração AO VIVO da Malu — converse com ela pelo teclado.

Uso (no Git Bash, com o venv ativo):
    python scripts/demo_chat.py

Você digita como se fosse um cliente; a Malu responde usando o mesmo
cérebro (Gemini + regras dela) que roda no WhatsApp. Quando ela montar o
briefing, ele aparece destacado. Digite 'sair' para encerrar.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Garante acentos/emojis no terminal do Windows, mesmo sem PYTHONUTF8
for _stream in (sys.stdout, sys.stdin, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ai import route_and_ask  # noqa: E402
from app.briefing import extract_briefing, parse_lead_temp  # noqa: E402

LINHA = "═" * 64
SAIR = {"sair", "exit", "quit", "fim", "tchau"}


def cabecalho() -> None:
    print("\n" + LINHA)
    print("  DEMONSTRAÇÃO — Malu, a assistente da Lu Milhas & Viagens")
    print(LINHA)
    print("  Digite como se você fosse um cliente no WhatsApp.")
    print("  A Malu vai responder na hora. Para encerrar, digite: sair")
    print(LINHA + "\n")


async def run() -> None:
    cabecalho()
    history: list[dict] = []

    while True:
        try:
            user_msg = input("VOCÊ (cliente):  ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nEncerrando a demonstração. Até logo!")
            return

        if not user_msg:
            continue
        if user_msg.lower() in SAIR:
            print("\nEncerrando a demonstração. Até logo!")
            return

        history.append({"role": "user", "content": user_msg})

        print("\n   ...Malu está digitando...\n")
        reply, model = await route_and_ask(history)
        history.append({"role": "assistant", "content": reply})

        etiqueta = "MALU" if model != "error" else "MALU (erro técnico)"
        print(f"{etiqueta}:  {reply}\n")
        print("-" * 64 + "\n")

        briefing = extract_briefing(reply)
        if briefing:
            print("█" * 64)
            print("  BRIEFING PRONTO — é isto que a Luciana recebe no WhatsApp dela")
            print("█" * 64)
            print(f"  Temperatura do lead: {parse_lead_temp(briefing)}\n")
            print(briefing)
            print("█" * 64 + "\n")
            print("Pode continuar conversando ou digitar 'sair' para encerrar.\n")


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\nencerrado")

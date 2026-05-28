"""Simula uma conversa completa com a Malu — sem precisar do WhatsApp real.

Uso:
    python scripts/seed_test.py

Faz chamadas diretas em `route_and_ask`, imprime cada turno, e ao final
mostra o briefing extraído (se houver).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Permite rodar `python scripts/seed_test.py` direto da raiz do projeto
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ai import route_and_ask  # noqa: E402
from app.briefing import extract_briefing, parse_lead_temp  # noqa: E402

# Conversa simulada — cobre o fluxo completo do prompt da Malu
USER_TURNS = [
    "Oi, quero viajar para Cancún em julho",
    "Somos 2 adultos, sem crianças, e queremos pacote com hospedagem",
    "Saída de Guarulhos. Ida dia 12/07 e volta dia 22/07",
    "Hospedagem com café da manhã, perto da praia. Categoria intermediária",
    "Bagagem despachada. Preferência por voo direto se fizer sentido no valor",
    "Orçamento aproximado de 8 mil por pessoa, incluindo aéreo e hospedagem",
    "Pagamento em dinheiro. Viagem de lua de mel. Pretendo fechar nas próximas semanas",
    "Sem necessidades especiais, sem passaporte vencido. Acho que é só isso!",
]


async def run() -> None:
    history: list[dict] = []

    # Pequeno delay entre turnos. Groq tem rate limit alto (6000 RPM no free),
    # mas 1s ajuda a evitar burst em ambientes mais restritivos.
    TURN_DELAY_S = 1

    for i, user_msg in enumerate(USER_TURNS, 1):
        if i > 1:
            await asyncio.sleep(TURN_DELAY_S)

        print(f"\n{'=' * 70}")
        print(f"TURNO {i}")
        print(f"{'=' * 70}")
        print(f"👤 CLIENTE: {user_msg}")

        history.append({"role": "user", "content": user_msg})

        reply, model = await route_and_ask(history)
        history.append({"role": "assistant", "content": reply})

        print(f"\n🤖 MALU ({model}):\n{reply}")

        briefing = extract_briefing(reply)
        if briefing:
            print("\n" + "█" * 70)
            print("📋 BRIEFING DETECTADO — fluxo encerraria aqui")
            print("█" * 70)
            print(f"Temperatura: {parse_lead_temp(briefing)}")
            print()
            print(briefing)
            return

    print("\n" + "─" * 70)
    print("Conversa terminou sem briefing — Malu ainda coletando dados.")
    print("─" * 70)


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\nencerrado pelo usuário")

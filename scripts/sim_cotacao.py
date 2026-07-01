"""Teste automatizado: 9 conversas (3 tipos de serviço × 3 cenários cada).

Roda o pipeline REAL (AI + Supabase) mas substitui o envio WhatsApp por print.
As 9 conversas são gravadas no banco com telefones de teste (5511900000001..9).
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

for _s in (sys.stdout, sys.stdin, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.main as m  # noqa: E402

LINHA = "═" * 72

# ── mocks ─────────────────────────────────────────────────────────────────────

async def fake_send(to: str, text: str) -> bool:
    print(f"\n🤖 MALU:\n{text}\n")
    print("─" * 72)
    return True


async def fake_notify(briefing: str, phone: str) -> None:
    print("\n" + "█" * 72)
    print("  📨 BRIEFING ENVIADO À LU")
    print("█" * 72)
    print(briefing)
    print("█" * 72 + "\n")


async def fake_notify_ret(phone: str, name) -> None:
    print(f"\n📨 [LU NOTIFICADA] cliente recorrente: {name}\n")


m.send_message = fake_send
m.notify_luciana = fake_notify
m.notify_luciana_returning_client = fake_notify_ret


# ── helpers ───────────────────────────────────────────────────────────────────

def payload(phone: str, name: str, text: str) -> dict:
    return {
        "entry": [{"changes": [{"value": {
            "messaging_product": "whatsapp",
            "contacts": [{"profile": {"name": name}, "wa_id": phone}],
            "messages": [{
                "from": phone,
                "id": f"wamid.{time.time_ns()}",
                "timestamp": "0",
                "type": "text",
                "text": {"body": text},
            }],
        }}]}]
    }


async def reset(phone: str) -> None:
    from app.session import clear_history, clear_state
    for fn in (clear_history, clear_state):
        try:
            await fn(phone)
        except Exception:
            pass
    try:
        from sqlalchemy import delete
        from app.database import SessionLocal
        from app.models import Conversation
        async with SessionLocal() as db:
            await db.execute(delete(Conversation).where(Conversation.phone == phone))
            await db.commit()
    except Exception:
        pass


# ── cenários ──────────────────────────────────────────────────────────────────

CENARIOS: list[dict] = [
    # ═══════════════════════ PASSAGEM AÉREA IDA E VOLTA ═══════════════════════
    dict(
        phone="5511900000001", name="Ana Teste",
        title="Passagem Aérea Ida e Volta — #1",
        msgs=[
            "Oi, bom dia!",
            "Quero passagem aérea ida e volta",
            "Destino Rio de Janeiro. Saindo de São Paulo dia 15 de julho, voltando dia 22 de julho",
            "Somos 2 adultos, sem crianças, classe econômica",
            "Sem preferência de companhia, 1 mala despachada por pessoa, quero pagar no cartão de crédito",
        ],
    ),
    dict(
        phone="5511900000002", name="Bruno Teste",
        title="Passagem Aérea Ida e Volta — #2",
        msgs=[
            "Boa tarde",
            "Opção 1",
            "Buenos Aires. Ida dia 10/08, volta dia 20/08",
            "Somos 3 adultos, sem crianças",
            "Classe executiva se possível, prefiro Latam. Bagagem despachada. Pix",
        ],
    ),
    dict(
        phone="5511900000003", name="Carla Teste",
        title="Passagem Aérea Ida e Volta — #3",
        msgs=[
            "Oi",
            "1",
            "Orlando. Partir em 20/11, voltar em 27/11",
            "1 adulto e 1 criança de 8 anos",
            "Econômica, Azul ou Gol, não preciso de bagagem despachada, boleto",
        ],
    ),

    # ═══════════════════════ PASSAGEM + HOSPEDAGEM ════════════════════════════
    dict(
        phone="5511900000004", name="Diego Teste",
        title="Passagem + Hospedagem — #1",
        msgs=[
            "Oi!",
            "Passagem e hotel",
            "Cancún, saindo dia 5 de setembro e voltando dia 12",
            "Casal, 2 adultos, classe econômica, qualquer companhia, 1 mala cada",
            "Hotel 4 estrelas frente ao mar se possível, 1 quarto casal, café da manhã incluso",
            "Cartão de crédito",
        ],
    ),
    dict(
        phone="5511900000005", name="Edilene Teste",
        title="Passagem + Hospedagem — #2",
        msgs=[
            "Boa noite",
            "2",
            "Lisboa, de 10 a 20 de outubro",
            "2 adultos, econômica, TAP ou Latam, bagagem despachada",
            "Hotel 3 estrelas no centro histórico, 1 quarto, café da manhã",
            "Pix",
        ],
    ),
    dict(
        phone="5511900000006", name="Fábio Teste",
        title="Passagem + Hospedagem — #3",
        msgs=[
            "Bom dia",
            "quero passagem mais hotel",
            "Fernando de Noronha, ida 15/01 volta 22/01",
            "2 adultos (eu e minha esposa), econômica, Azul, só bagagem de mão",
            "Pousada boa com vista pro mar, 1 quarto, meia pensão",
            "Cartão parcelado",
        ],
    ),

    # ═══════════════════════════ PACOTE COMPLETO ══════════════════════════════
    dict(
        phone="5511900000007", name="Giovana Teste",
        title="Pacote Completo — #1",
        msgs=[
            "Oi",
            "3",
            "Paris, de 20 a 30 de dezembro",
            "2 adultos, classe executiva, Air France, 2 malas despachadas",
            "Hotel 5 estrelas perto da Torre Eiffel, 1 suíte, café da manhã",
            "Sim, quero city tour, Museu do Louvre e passeio de barco. Transfer aeroporto sim",
            "Cartão em 12x",
        ],
    ),
    dict(
        phone="5511900000008", name="Henrique Teste",
        title="Pacote Completo — #2",
        msgs=[
            "Boa tarde",
            "Quero um pacote completo",
            "Dubai, de 2 a 12 de novembro",
            "2 adultos e 2 crianças de 6 e 10 anos",
            "Econômica, Emirates, 3 malas despachadas",
            "Resort all inclusive 5 estrelas, 2 quartos ou suíte família",
            "Safari no deserto e Burj Khalifa. Transfer e guia em português",
            "Cartão de crédito",
        ],
    ),
    dict(
        phone="5511900000009", name="Isabela Teste",
        title="Pacote Completo — #3",
        msgs=[
            "Boa tarde",
            "opção 3",
            "Maldivas, ida 14 de fevereiro, volta 21 de fevereiro",
            "Lua de mel, 2 adultos, classe executiva, sem preferência de companhia, 1 mala cada",
            "Overwater bungalow, 1 bangalô, all inclusive",
            "Jantar romântico e snorkeling. Transfer de speedboat do aeroporto",
            "Pix ou cartão, o que for melhor pra mim",
        ],
    ),
]


# ── runner ────────────────────────────────────────────────────────────────────

async def run_scenario(s: dict) -> None:
    print(f"\n\n{'#' * 72}")
    print(f"  CENÁRIO: {s['title']}")
    print(f"  Telefone: {s['phone']}  ·  Nome: {s['name']}")
    print(f"{'#' * 72}\n")

    await reset(s["phone"])

    for i, msg in enumerate(s["msgs"], 1):
        print(f"[{i}/{len(s['msgs'])}] 👤 VOCÊ: {msg}")
        await m.handle_message(payload(s["phone"], s["name"], msg))
        await asyncio.sleep(1.5)

    print(f"\n{'#' * 72}")
    print(f"  FIM: {s['title']}")
    print(f"{'#' * 72}\n")


async def main() -> None:
    print(f"\n{LINHA}")
    print("  TESTE AUTOMATIZADO — 9 conversas (3 modelos × 3 cenários)")
    print(f"{LINHA}\n")

    for cenario in CENARIOS:
        await run_scenario(cenario)
        await asyncio.sleep(3.0)

    try:
        from app.session import close_redis
        await close_redis()
    except Exception:
        pass

    print(f"\n{LINHA}")
    print("  TODOS OS CENARIOS CONCLUIDOS")
    print(f"{LINHA}\n")


if __name__ == "__main__":
    asyncio.run(main())

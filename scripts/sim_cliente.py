"""Simula um cliente conversando com a Malu pelo PIPELINE REAL.

Roda exatamente o `handle_message` do webhook (grava conversa + lead no banco,
gera briefing), mas substitui o ENVIO ao WhatsApp por uma impressão na tela —
assim dá pra testar tudo localmente sem número e ver o resultado no painel.

Uso (venv ativo):
    python scripts/sim_cliente.py
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.main as m  # noqa: E402

PHONE = "5511977776666"
NAME = "Ana Teste"


async def fake_send(to: str, text: str) -> bool:
    print(f"\n   🤖 MALU →:\n   {text}\n")
    return True


async def fake_notify(briefing: str, phone: str) -> None:
    print("\n   📨 [NOTIFICAÇÃO PARA A LU — chega no WhatsApp PESSOAL dela]")
    print("   (a Lu recebe o briefing pronto e assume o cliente pelo número dela)\n")


async def fake_notify_ret(phone: str, name) -> None:
    print(f"\n   📨 [NOTIFICAÇÃO PARA A LU] cliente recorrente {name} quer atendimento\n")


# Substitui envios reais (sem número válido ainda) por impressão
m.send_message = fake_send
m.notify_luciana = fake_notify
m.notify_luciana_returning_client = fake_notify_ret


def payload(text: str) -> dict:
    return {
        "entry": [{
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "contacts": [{"profile": {"name": NAME}, "wa_id": PHONE}],
                    "messages": [{
                        "from": PHONE,
                        "id": f"wamid.SIM{time.time()}",
                        "timestamp": "0",
                        "type": "text",
                        "text": {"body": text},
                    }],
                }
            }]
        }]
    }


TURNS = [
    "Oi, quero um pacote pra Porto Seguro em setembro",
    "Somos 2 adultos e 1 criança de 7 anos, e meu nome é Ana",
    "Saindo de São Paulo, de 10 a 17 de setembro. Meu WhatsApp é 11977776666",
    "Hospedagem com café da manhã, perto da praia, categoria intermediária, um quarto família",
    "Com bagagem despachada, voo direto se der",
    "Orçamento uns 5 mil por pessoa, pagamento no cartão",
    "É viagem de férias em família, quero fechar essa semana, sem necessidades especiais",
    "Acho que é só isso! Pode montar o resumo pra Lu",
]


async def _reset_session() -> None:
    """Limpa histórico/estado da sessão pra um teste limpo."""
    from app.session import clear_history, clear_state
    try:
        await clear_history(PHONE)
        await clear_state(PHONE)
    except Exception:
        pass


async def main() -> None:
    print("=" * 64)
    print(f"  SIMULAÇÃO — cliente '{NAME}' ({PHONE}) falando com a Malu")
    print("  (grava no banco PROD; veja depois no painel localhost:3000)")
    print("=" * 64)
    await _reset_session()
    for t in TURNS:
        print("\n" + "─" * 64)
        print(f"👤 CLIENTE: {t}")
        await m.handle_message(payload(t))
        await asyncio.sleep(1.2)
    print("\n" + "=" * 64)
    print("  FIM. Abra o painel (localhost:3000) e veja o lead 'Ana Teste'.")
    print("=" * 64)


if __name__ == "__main__":
    asyncio.run(main())

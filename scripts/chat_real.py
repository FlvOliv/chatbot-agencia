"""Converse com a Malu pelo TECLADO e pelo PIPELINE REAL (grava no CRM).

Junta o melhor dos dois scripts:
  - como o demo_chat.py: você digita ao vivo e a Malu responde;
  - como o sim_cliente.py: roda o `handle_message` de verdade, então
    grava conversa + lead no banco e aparece no painel (localhost:3000).

O envio ao WhatsApp é trocado por impressão na tela (ainda não temos
número válido). Assim dá pra testar TUDO localmente:

  1) você conversa com a Malu (ela responde, grava no CRM);
  2) sem fechar este script, abra o painel → Conversas → sua conversa
     → "Assumir": a Malu fica em silêncio (você vira a Lu);
  3) responda pelo painel e veja aparecer na conversa;
  4) "Devolver" no painel → a Malu volta a responder aqui.

Uso (venv ativo):
    python scripts/chat_real.py
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

# Acentos/emojis no terminal do Windows
for _s in (sys.stdout, sys.stdin, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.main as m  # noqa: E402

# Cliente que é VOCÊ. Número fresco pra não misturar com as demos antigas.
PHONE = "5511955554444"
NAME = "Flávio (teste)"

LINHA = "═" * 64
SAIR = {"sair", "exit", "quit", "fim", "tchau"}


async def fake_send(to: str, text: str) -> bool:
    """No lugar de mandar no WhatsApp, mostra a resposta da Malu aqui."""
    print(f"\n🤖 MALU:\n{text}\n")
    print("─" * 64)
    return True


async def fake_notify(briefing: str, phone: str) -> None:
    print("\n" + "█" * 64)
    print("  📨 BRIEFING PRONTO — é isto que a Lu recebe no WhatsApp dela")
    print("█" * 64)
    print(briefing)
    print("█" * 64 + "\n")


async def fake_notify_ret(phone: str, name) -> None:
    print(f"\n📨 [NOTIFICAÇÃO PARA A LU] cliente recorrente {name} quer atendimento\n")


# Troca os envios reais por impressão na tela
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
                        "id": f"wamid.CHAT{time.time()}",
                        "timestamp": "0",
                        "type": "text",
                        "text": {"body": text},
                    }],
                }
            }]
        }]
    }


async def _reset_session() -> None:
    """Começa do zero: limpa a memória da Malu (Redis) e o histórico no banco.

    Apaga SÓ as linhas deste número de teste — nada das conversas reais.
    """
    from app.session import clear_history, clear_state
    # Blocos separados: se um falhar, o outro ainda roda (estado precisa zerar)
    try:
        await clear_history(PHONE)
    except Exception:
        pass
    try:
        await clear_state(PHONE)
    except Exception:
        pass
    try:
        from sqlalchemy import delete
        from app.database import SessionLocal
        from app.models import Conversation
        async with SessionLocal() as db:
            await db.execute(delete(Conversation).where(Conversation.phone == PHONE))
            await db.commit()
    except Exception:
        pass


async def _watch_lu_replies(stop: asyncio.Event) -> None:
    """Mostra aqui as respostas que a Lu envia pelo painel (lê do banco).

    Fecha o ciclo visualmente sem WhatsApp: a mensagem da Lu (gravada como
    model_used='human') aparece como se o cliente tivesse recebido no celular.
    """
    from sqlalchemy import select
    from app.database import SessionLocal
    from app.models import Conversation

    seen: set = set()
    # Já existir alguma? Marca como vista (não deve haver, após o reset).
    try:
        async with SessionLocal() as db:
            ids = (await db.execute(
                select(Conversation.id).where(
                    Conversation.phone == PHONE,
                    Conversation.role == "assistant",
                    Conversation.model_used == "human",
                )
            )).scalars().all()
            seen.update(ids)
    except Exception:
        pass

    while not stop.is_set():
        try:
            async with SessionLocal() as db:
                rows = (await db.execute(
                    select(Conversation.id, Conversation.content)
                    .where(
                        Conversation.phone == PHONE,
                        Conversation.role == "assistant",
                        Conversation.model_used == "human",
                    )
                    .order_by(Conversation.created_at)
                )).all()
            for rid, content in rows:
                if rid not in seen:
                    seen.add(rid)
                    print(f"\n👩 LU (resposta pelo painel):\n{content}\n")
                    print("─" * 64)
                    print("VOCÊ (cliente):  ", end="", flush=True)
        except Exception:
            pass
        await asyncio.sleep(2.0)


def cabecalho() -> None:
    print("\n" + LINHA)
    print("  CHAT REAL — você conversando com a Malu (grava no CRM)")
    print(LINHA)
    print(f"  Sua conversa no painel:  {NAME}  ·  {PHONE}")
    print("  Digite como cliente. Para encerrar: sair")
    print("  (Pra testar o 'Assumir': deixe este chat aberto e use o painel.)")
    print(LINHA + "\n")


async def main() -> None:
    cabecalho()
    await _reset_session()

    # "Ouvinte" das respostas da Lu (painel) rodando em segundo plano
    stop = asyncio.Event()
    watcher = asyncio.create_task(_watch_lu_replies(stop))

    loop = asyncio.get_event_loop()
    try:
        while True:
            try:
                # input() numa thread → o event loop segue vivo (grava/ouve em segundo plano)
                user_msg = (await loop.run_in_executor(None, input, "VOCÊ (cliente):  ")).strip()
            except (EOFError, KeyboardInterrupt):
                break

            if not user_msg:
                continue
            if user_msg.lower() in SAIR:
                break

            print("\n   ...Malu está processando...")
            await m.handle_message(payload(user_msg))
            # dá um tempinho pra gravação em segundo plano concluir
            await asyncio.sleep(0.8)
    finally:
        # Encerra o ouvinte e fecha conexões com elegância
        stop.set()
        watcher.cancel()
        try:
            await watcher
        except (asyncio.CancelledError, Exception):
            # CancelledError herda de BaseException — precisa ser pega explicitamente
            pass
        await asyncio.sleep(1.0)
        try:
            from app.session import close_redis
            await close_redis()
        except Exception:
            pass
        print("\nEncerrado. Veja a conversa no painel: http://localhost:3000/conversas\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nencerrado")

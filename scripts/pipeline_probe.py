"""Harness de PIPELINE — dirige o `_process_text_message` REAL (com Alavancas
D/B/A + gate só-ida) usando IA real, mas com TODO o I/O externo stubbado:
nada vai pra Meta/Lu, sessão em fakeredis em memória, sem Postgres.

Mostra a Malu numa conversa de verdade e o que dispara a cada turno (modelo,
estado de coleta injetado [B], anti-loop [D], nudge do gate, finalização).

Uso:
    COLETA_STATE_ENABLED=true PYTHONUTF8=1 venv/Scripts/python -m scripts.pipeline_probe
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fakeredis import aioredis as fakeredis_aio  # noqa: E402

from app import main, session  # noqa: E402

TRANSCRIPT: dict[str, list[tuple[str, str]]] = {}
SIG: dict = {}
SLEEP_BETWEEN_TURNS = 5  # alivia rate limit da IA


# --- stubs de I/O externo (nada sai; nada toca banco) --------------------
class _FakeDB:
    async def commit(self):  # noqa: ANN001
        return None


class _FakeSession:
    async def __aenter__(self):  # noqa: ANN001
        return _FakeDB()

    async def __aexit__(self, *a):  # noqa: ANN001
        return False


async def _stub_send(to, text):  # noqa: ANN001
    SIG["reply"] = text
    return True


async def _stub_get_or_create(phone, profile, db):  # noqa: ANN001
    return SimpleNamespace(display_name=profile or "Cliente")


async def _stub_reserva(phone, db):  # noqa: ANN001
    return False


async def _stub_collect(phone, text):  # noqa: ANN001
    return [text]  # pula o debounce (1 msg = fala completa)


async def _stub_persist(phone, user_text, reply, model, user_media_path=None):  # noqa: ANN001
    TRANSCRIPT.setdefault(phone, [])
    if user_text:
        TRANSCRIPT[phone].append(("user", user_text))
    if reply:
        TRANSCRIPT[phone].append(("assistant", reply))


async def _stub_finalize(phone, history, briefing_block, data):  # noqa: ANN001
    SIG["finalized"] = True
    SIG["lead_data"] = data
    return 9999


async def _stub_noop(*a, **k):  # noqa: ANN001, ANN003
    return None


def _make_notify(name):  # noqa: ANN001
    async def _n(*a, **k):  # noqa: ANN001, ANN003
        SIG["notify"] = name
        return True

    return _n


def _install_stubs() -> None:
    main.SessionLocal = _FakeSession  # type: ignore[assignment]
    main.send_message = _stub_send  # type: ignore[assignment]
    main.get_or_create_cliente = _stub_get_or_create  # type: ignore[assignment]
    main.has_reserva_ativa = _stub_reserva  # type: ignore[assignment]
    main.collect_burst = _stub_collect  # type: ignore[assignment]
    main._persist_conversation = _stub_persist  # type: ignore[assignment]
    main._finalize_lead = _stub_finalize  # type: ignore[assignment]
    main.schedule_callbacks = _stub_noop  # type: ignore[assignment]
    main.cancel_reminders = _stub_noop  # type: ignore[assignment]
    main.send_push_to_all = _stub_noop  # type: ignore[assignment]
    main.update_preferred_name = _stub_noop  # type: ignore[assignment]
    for n in (
        "notify_luciana",
        "notify_luciana_returning_client",
        "notify_luciana_ai_down",
        "notify_luciana_media",
        "notify_luciana_impasse",
    ):
        setattr(main, n, _make_notify(n))

    # traça o contexto injetado (B / anti-loop) + o modelo que respondeu
    _real_route = main.route_and_ask

    async def _traced_route(history, customer_context=None):  # noqa: ANN001
        ctx = customer_context or {}
        SIG.setdefault("routes", []).append(
            {"anti_loop": bool(ctx.get("anti_loop")), "coleta_state": ctx.get("coleta_state")}
        )
        reply, model = await _real_route(history, customer_context=customer_context)
        SIG["routes"][-1]["model"] = model
        return reply, model

    main.route_and_ask = _traced_route  # type: ignore[assignment]


async def _turn(phone: str, name: str, msg: str) -> None:
    SIG.clear()
    SIG["routes"] = []
    await main._process_text_message(phone, msg, name)

    print(f"\n[CLIENTE] {msg}")
    for i, r in enumerate(SIG["routes"]):
        tag = " (RE-PROMPT anti-loop 🔁)" if r["anti_loop"] else ""
        print(f"   · chamada IA {i + 1}: modelo={r.get('model')}{tag}")
        if r["coleta_state"]:
            estado = r["coleta_state"].replace("\n", "\n        ")
            print(f"        [B injetou] {estado}")
    print(f"[MALU] {SIG.get('reply', '(sem resposta)')}")
    if SIG.get("notify"):
        print(f"   » ⚠️ passou pra Lu via {SIG['notify']}")
    if SIG.get("finalized"):
        print("   » ✅ FINALIZOU o lead (gate liberou)")
        print(f"   » extração: { {k: v for k, v in (SIG.get('lead_data') or {}).items() if v} }")


async def main_run() -> None:
    session.set_redis_client(fakeredis_aio.FakeRedis(decode_responses=True))
    _install_stubs()

    phone, name = "5511970000001", "Flávio"
    print("=" * 72)
    print("PIPELINE PROBE — conversa SÓ IDA (o bug do Flávio), pipeline REAL")
    print("=" * 72)

    turns = [
        "Oi, queria uma passagem só de ida de São Paulo pra Recife",
        "dia 20 de dezembro",
        "1 adulto",
        "tanto faz o aeroporto, o mais barato",  # não-resposta (D/B não podem loopar)
        "pode ser pix",
        "ninguém indicou",
    ]
    for t in turns:
        await _turn(phone, name, t)
        await asyncio.sleep(SLEEP_BETWEEN_TURNS)

    # --- Demo da Alavanca A: Redis "cai" → histórico reconstruído do Postgres ---
    print("\n" + "-" * 72)
    print("ALAVANCA A — simulando Redis fora no meio da conversa:")

    async def _hist_db(p):  # noqa: ANN001
        rows = TRANSCRIPT.get(p, [])[-20:]
        return [
            {"role": r, "content": c.removeprefix("🎤 ").strip()}
            for r, c in rows
            if r in ("user", "assistant") and c.strip()
        ]

    session._history_from_db = _hist_db  # type: ignore[assignment]

    async def _boom(key):  # noqa: ANN001
        raise RuntimeError("redis down (simulado)")

    session.get_redis().get = _boom  # type: ignore[assignment]
    recovered = await session.get_history(phone)
    print(f"   get_history com Redis fora → {len(recovered)} msgs reconstruídas do Postgres")
    print("   (sem isso, seria [] → is_first_turn=True → Malu RE-SAUDA)")
    print("\n" + "=" * 72 + "\nFIM\n")


if __name__ == "__main__":
    asyncio.run(main_run())

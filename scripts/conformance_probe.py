"""Suíte de CONFORMIDADE da Malu — cenários adversariais no pipeline REAL.

Evolução das sondas (behavior_probe/pipeline_probe): dirige o
`_process_text_message` REAL (Alavancas B/D + gate por tipo) com IA real e
I/O externo stubbado (nada vai pra Meta/Lu; sessão em fakeredis; sem Postgres),
mas agora com CHECAGENS AUTOMÁTICAS por cenário — o resultado é um veredito
✅/❌ por comportamento, não só um transcript pra ler.

Comportamentos checados (os 3 bugs + regressões conhecidas):
  C1  repetiu fala/pergunta (pares de respostas quase iguais — loop)
  C2  re-saudou no meio da conversa (amnésia)
  C3  vazou preço pro cliente (R$/valores na resposta enviada)
  C4  modelo TENTOU citar preço (price_guard disparou — mascarado, mas é
      comportamento do modelo a refinar)
  C5  finalizou quando esperado (e nunca ANTES do turno mínimo — fecho furado)
  C6  transferiu só quando devido
  C7  perguntou indicação antes de fechar
  C8  pós-fecho: silêncio (sem resposta nem 2º lead — bug dos duplicados)

Uso (Git Bash, venv ativo):
    COLETA_STATE_ENABLED=true PYTHONUTF8=1 venv/Scripts/python -m scripts.conformance_probe
    # ou só alguns cenários (economiza rate limit da IA):
    ... -m scripts.conformance_probe S3,S4
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
from dataclasses import dataclass, field
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

SLEEP_BETWEEN_TURNS = 6  # alivia rate limit da IA
SLEEP_BETWEEN_SCENARIOS = 10

# Valores monetários na fala da MALU (não do cliente) = vazamento.
_PRICE_LEAK_RE = re.compile(r"R\$\s*\d|\b\d[\d.,]*\s*(mil|reais)\b", re.IGNORECASE)
_GREET_RE = re.compile(r"\bsou a malu\b", re.IGNORECASE)
_INDIC_RE = re.compile(r"\bindic", re.IGNORECASE)


# ---------------------------------------------------------------- cenários --
@dataclass
class Scenario:
    key: str
    title: str
    phone: str
    name: str
    turns: list[str]
    expect_finalize: bool
    # turno (1-based) ANTES do qual finalizar = fecho furado (None = sem piso)
    min_finalize_turn: int | None = None
    # None = não pode transferir; True = deve; "allowed" = aceitável (impasse §6)
    expect_transfer: object = None
    # último turno é um "obrigado" PÓS-fecho → checa silêncio + sem 2º lead
    gratitude_tail: bool = False


SCENARIOS: list[Scenario] = [
    Scenario(
        key="S1",
        title="Cruzeiro da tia (03/07) — período vago é COMPLETO p/ cruzeiro",
        phone="5511970000101",
        name="Regina",
        turns=[
            "Oi! Queria ver um cruzeiro pro Nordeste",
            "Pode ser saindo de Santos",
            "Primeira quinzena de dezembro, uns 5 a 7 dias. Não sei os dias que os navios partem",
            "Vamos eu e meu marido, 2 adultos",
            "Pode ser à vista no pix",
            "Ninguém indicou não, achei no Instagram",
            "Obrigada, você é um amor!",
        ],
        expect_finalize=True,
        gratitude_tail=True,
    ),
    Scenario(
        key="S2",
        title="Tudo de uma vez — não pode reperguntar o já dado + sem lead duplicado",
        phone="5511970000102",
        name="Paulo",
        turns=[
            "Oi Malu! Quero passagem de Curitiba pra Fortaleza, ida 15/01 e volta 22/01, "
            "2 adultos e 1 bebê de 1 ano, de preferência voo direto",
            "Pagamento tanto faz, o que compensar mais",
            "Foi minha prima Ana que indicou a Lu",
            "Perfeito, obrigado!",
        ],
        expect_finalize=True,
        gratitude_tail=True,
    ),
    Scenario(
        key="S3",
        title="Caso #1030 — pressa + valor + data vaga (não fechar furado)",
        phone="5511970000103",
        name="Diego",
        turns=[
            "Oi, quero uma cotação pra Paris saindo de SP mês que vem, fico 5 dias",
            "Tenho uns 15 mil guardados, dá pra fazer algo bom?",
            "Me manda logo a cotação, já finalizou?",
            "Tá bom: ida 10 de agosto e volta 15 de agosto",
            "2 adultos",
            "Ninguém me indicou",
        ],
        expect_finalize=True,
        min_finalize_turn=4,  # só há data concreta a partir do turno 4
    ),
    Scenario(
        key="S4",
        title="Só ida (bug do Flávio) — não insistir na volta",
        phone="5511970000104",
        name="Flávio",
        turns=[
            "Oi, preciso de uma passagem só de ida de São Paulo pra Recife",
            "dia 20 de dezembro",
            "só eu, 1 adulto",
            "pode ser pix",
            "ninguém me indicou",
            "valeu!",
        ],
        expect_finalize=True,
        gratitude_tail=True,
    ),
    Scenario(
        key="S5",
        title="Enrolação — cliente vago; anti-loop não pode repetir 3×",
        phone="5511970000105",
        name="Bianca",
        turns=[
            "Oi, quero viajar",
            "ainda não sei pra onde, me ajuda a escolher",
            "hmm tanto faz",
            "não sei mesmo",
        ],
        expect_finalize=False,
        expect_transfer="allowed",  # impasse §6 → Lu assume é aceitável
    ),
    Scenario(
        key="S6",
        title="Pede atendente — transferência legítima",
        phone="5511970000106",
        name="Carla",
        turns=[
            "Oi, queria uma cotação de passagem pra Lisboa em março, saindo de SP",
            "Prefiro falar com uma pessoa de verdade, pode chamar a atendente?",
        ],
        expect_finalize=False,
        expect_transfer=True,
    ),
]


# ------------------------------------------------------------------- stubs --
SIG: dict = {}


class _FakeDB:
    async def commit(self):  # noqa: ANN001
        return None


class _FakeSession:
    async def __aenter__(self):  # noqa: ANN001
        return _FakeDB()

    async def __aexit__(self, *a):  # noqa: ANN001
        return False


async def _stub_send(to, text):  # noqa: ANN001
    SIG.setdefault("sent", []).append(text)
    return True


async def _stub_get_or_create(phone, profile, db):  # noqa: ANN001
    return SimpleNamespace(display_name=profile or "Cliente")


async def _stub_reserva(phone, db):  # noqa: ANN001
    return False


async def _stub_collect(phone, text):  # noqa: ANN001
    return [text]  # 1 msg = fala completa (pula debounce)


async def _stub_persist(*a, **k):  # noqa: ANN001, ANN003
    return None


async def _stub_finalize(phone, history, briefing_block, data):  # noqa: ANN001
    SIG.setdefault("finalized", []).append(dict(data or {}))
    return 9999


async def _stub_noop(*a, **k):  # noqa: ANN001, ANN003
    return None


def _make_notify(name):  # noqa: ANN001
    async def _n(*a, **k):  # noqa: ANN001, ANN003
        SIG.setdefault("notify", []).append(name)
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

    # rastreia price_guard (modelo tentou citar valor, mesmo que mascarado)
    _real_guard = main.price_guard

    def _traced_guard(text):  # noqa: ANN001
        out, blocked = _real_guard(text)
        if blocked:
            SIG["price_attempt"] = True
        return out, blocked

    main.price_guard = _traced_guard  # type: ignore[assignment]

    # rastreia contexto injetado (B) + re-prompt anti-loop (D) + modelo
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


# --------------------------------------------------------------- execução --
@dataclass
class TurnRec:
    user: str
    replies: list[str]
    routes: list[dict]
    notify: list[str]
    finalized: list[dict]
    price_attempt: bool


@dataclass
class ScenarioResult:
    scenario: Scenario
    turns: list[TurnRec] = field(default_factory=list)

    @property
    def malu_replies(self) -> list[tuple[int, str]]:
        return [(i, r) for i, t in enumerate(self.turns, 1) for r in t.replies]

    @property
    def finalize_turn(self) -> int | None:
        for i, t in enumerate(self.turns, 1):
            if t.finalized:
                return i
        return None

    @property
    def all_notifies(self) -> list[str]:
        return [n for t in self.turns for n in t.notify]

    @property
    def total_leads(self) -> int:
        return sum(len(t.finalized) for t in self.turns)


async def run_scenario(sc: Scenario) -> ScenarioResult:
    res = ScenarioResult(sc)
    print("\n" + "=" * 72)
    print(f"{sc.key} · {sc.title}")
    print("=" * 72)

    for msg in sc.turns:
        SIG.clear()
        await main._process_text_message(sc.phone, msg, sc.name)
        rec = TurnRec(
            user=msg,
            replies=list(SIG.get("sent", [])),
            routes=list(SIG.get("routes", [])),
            notify=list(SIG.get("notify", [])),
            finalized=list(SIG.get("finalized", [])),
            price_attempt=bool(SIG.get("price_attempt")),
        )
        res.turns.append(rec)

        print(f"\n[CLIENTE] {msg}")
        for r in rec.routes:
            tag = " (RE-PROMPT anti-loop 🔁)" if r["anti_loop"] else ""
            print(f"   · IA: modelo={r.get('model')}{tag}")
            if r["coleta_state"]:
                estado = str(r["coleta_state"]).replace("\n", "\n        ")
                print(f"        [B injetou] {estado}")
        if rec.replies:
            for r in rec.replies:
                print(f"[MALU] {r}")
        else:
            print("[MALU] (silêncio)")
        if rec.price_attempt:
            print("   » ⚠️ price_guard DISPAROU (modelo tentou citar valor)")
        for n in rec.notify:
            print(f"   » 📣 avisou a Lu via {n}")
        if rec.finalized:
            data = {k: v for k, v in rec.finalized[0].items() if v}
            print(f"   » ✅ FINALIZOU lead — extração: {data}")

        await asyncio.sleep(SLEEP_BETWEEN_TURNS)
    return res


# ------------------------------------------------------------ conformidade --
@dataclass
class Check:
    code: str
    label: str
    ok: bool | None  # None = alerta (não reprova)
    detail: str = ""


def evaluate(res: ScenarioResult) -> list[Check]:
    sc = res.scenario
    checks: list[Check] = []
    replies = res.malu_replies
    fin_turn = res.finalize_turn
    n_turns = len(res.turns)
    tail_start = n_turns if sc.gratitude_tail else None

    # C1 repetição (pares quase iguais entre respostas da Malu, fora o tail)
    dupes = []
    core = [(t, r) for t, r in replies if tail_start is None or t < tail_start]
    for a in range(len(core)):
        for b in range(a + 1, len(core)):
            if main._too_similar(core[a][1], core[b][1]):
                dupes.append(f"turnos {core[a][0]}≈{core[b][0]}")
    checks.append(
        Check("C1", "não repetiu fala/pergunta", not dupes, "; ".join(dupes))
    )

    # C2 re-saudação (amnésia) — "sou a Malu" só vale no 1º turno
    regreet = [t for t, r in replies if t > 1 and _GREET_RE.search(r)]
    checks.append(
        Check("C2", "não re-saudou no meio", not regreet,
              f"turnos {regreet}" if regreet else "")
    )

    # C3 preço VAZOU na resposta enviada
    leaks = [t for t, r in replies if _PRICE_LEAK_RE.search(r)]
    checks.append(
        Check("C3", "não vazou preço pro cliente", not leaks,
              f"turnos {leaks}" if leaks else "")
    )

    # C4 modelo TENTOU citar preço (guard mascarou) — alerta, não reprova
    attempts = [i for i, t in enumerate(res.turns, 1) if t.price_attempt]
    checks.append(
        Check("C4", "modelo nem tentou citar preço",
              None if attempts else True,
              f"price_guard disparou nos turnos {attempts}" if attempts else "")
    )

    # C5 finalização conforme esperado (e não antes do piso)
    if sc.expect_finalize:
        if fin_turn is None:
            checks.append(Check("C5", "finalizou o lead", False, "nunca finalizou"))
        elif sc.min_finalize_turn and fin_turn < sc.min_finalize_turn:
            checks.append(
                Check("C5", "finalizou o lead", False,
                      f"fechou FURADO no turno {fin_turn} (< {sc.min_finalize_turn})")
            )
        else:
            checks.append(Check("C5", "finalizou o lead", True, f"turno {fin_turn}"))
    else:
        checks.append(
            Check("C5", "NÃO finalizou (como esperado)", fin_turn is None,
                  f"finalizou no turno {fin_turn}" if fin_turn else "")
        )

    # C6 transferência
    transfers = [
        n for n in res.all_notifies
        if n in ("notify_luciana_returning_client", "notify_luciana_impasse",
                 "notify_luciana_ai_down")
    ]
    if sc.expect_transfer is True:
        checks.append(
            Check("C6", "transferiu pra Lu", bool(transfers), ", ".join(transfers))
        )
    elif sc.expect_transfer == "allowed":
        checks.append(
            Check("C6", "transferência (aceitável se impasse)", True,
                  ", ".join(transfers) or "não transferiu (seguiu coletando)")
        )
    else:
        checks.append(
            Check("C6", "não transferiu indevidamente", not transfers,
                  ", ".join(transfers))
        )

    # C7 indicação perguntada antes do fecho
    if fin_turn is not None:
        asked = [t for t, r in replies if t <= fin_turn and _INDIC_RE.search(r)]
        # a pergunta pode ter vindo da própria fala final do cliente; o que
        # importa é a MALU ter perguntado em algum turno até o fecho
        checks.append(
            Check("C7", "perguntou indicação antes de fechar", bool(asked),
                  f"turnos {asked}" if asked else "nunca perguntou")
        )

    # C8 pós-fecho: silêncio e sem lead duplicado
    if sc.gratitude_tail and fin_turn is not None:
        tail = res.turns[-1]
        silent = not tail.replies and not tail.finalized
        checks.append(
            Check("C8", "pós-fecho: calada e sem 2º lead", silent,
                  f"respondeu={bool(tail.replies)} novo_lead={bool(tail.finalized)}")
        )
    if res.total_leads > 1:
        checks.append(
            Check("C8b", "1 lead só", False, f"{res.total_leads} leads criados!")
        )

    return checks


def print_report(all_results: list[tuple[ScenarioResult, list[Check]]]) -> int:
    print("\n" + "#" * 72)
    print("RELATÓRIO DE CONFORMIDADE")
    print("#" * 72)
    failures = 0
    for res, checks in all_results:
        sc = res.scenario
        fails = [c for c in checks if c.ok is False]
        warns = [c for c in checks if c.ok is None]
        status = "❌ REPROVOU" if fails else ("⚠️ ALERTAS" if warns else "✅ PASSOU")
        failures += len(fails)
        print(f"\n{sc.key} · {sc.title}\n   → {status}")
        for c in checks:
            icon = "✅" if c.ok else ("⚠️" if c.ok is None else "❌")
            detail = f"  — {c.detail}" if c.detail else ""
            print(f"   {icon} {c.code} {c.label}{detail}")
        if res.finalize_turn:
            data = {k: v for k, v in res.turns[res.finalize_turn - 1].finalized[0].items() if v}
            print(f"   📋 lead extraído: {data}")
    print(f"\n{'—' * 72}\nTOTAL: {failures} falha(s) de conformidade\n")
    return failures


async def main_run() -> None:
    session.set_redis_client(fakeredis_aio.FakeRedis(decode_responses=True))
    _install_stubs()

    print("SUÍTE DE CONFORMIDADE — Malu (pipeline REAL, IA real, sem envio)")
    from app.config import settings

    # Contorno de cota (opcional): PROBE_AI_PRIMARY=cerebras faz a cadeia
    # começar noutro provider quando o Groq estourou o dia (TPD). Atribuição
    # direta pula a validação Literal do pydantic — aceitável num harness
    # (o AI_PRIMARY de verdade segue groq em produção).
    override = os.environ.get("PROBE_AI_PRIMARY")
    if override:
        settings.ai_primary = override  # type: ignore[assignment]
        print(f"⚠️ ai_primary sobrescrito p/ este teste: {override}")

    print(f"coleta_state_enabled = {settings.coleta_state_enabled}")

    keys = set(sys.argv[1].split(",")) if len(sys.argv) > 1 else None
    all_results: list[tuple[ScenarioResult, list[Check]]] = []
    for sc in SCENARIOS:
        if keys is not None and sc.key not in keys:
            continue
        try:
            res = await run_scenario(sc)
            all_results.append((res, evaluate(res)))
        except Exception as exc:  # 1 cenário não derruba os outros
            print(f"\n[ERRO no cenário {sc.key}] {type(exc).__name__}: {exc}")
        await asyncio.sleep(SLEEP_BETWEEN_SCENARIOS)

    failures = print_report(all_results)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    asyncio.run(main_run())

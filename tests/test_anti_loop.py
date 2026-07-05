"""Testes da Alavanca D — anti-loop (Malu não repete a mesma pergunta)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app import main
from app.ai import _build_system_prompt

# Pergunta "opcional" longa que o cliente não responde (o loop observado no T2).
LOOP_Q = (
    "Qual aeroporto de preferência no Rio — Galeão (GIG) ou Santos Dumont (SDU)? "
    "E qual a forma de pagamento que você prefere?"
)
# Resposta que AVANÇA (não é loop) — usada quando o re-prompt quebra o loop.
ADVANCE = (
    "Perfeito! Anotei sem preferência de aeroporto. Vamos seguir: quantas pessoas "
    "vão viajar, contando adultos e crianças com as idades?"
)


# ---------------------------------------------------------------------------
# Unit — detector de repetição
# ---------------------------------------------------------------------------
def test_too_similar_pega_repeticao_quase_verbatim() -> None:
    quase = LOOP_Q.replace("prefere?", "prefere mesmo?")
    assert main._too_similar(LOOP_Q, quase) is True


def test_too_similar_ignora_perguntas_diferentes() -> None:
    assert main._too_similar(LOOP_Q, ADVANCE) is False


def test_too_similar_ignora_mensagens_curtas() -> None:
    # Saudações/confirmações curtas não contam como loop, mesmo idênticas.
    assert main._too_similar("Perfeito! 😊", "Perfeito! 😊") is False


# A fixação do cenário S4 (05/07): a MESMA sub-pergunta (aeroporto) re-embutida
# em frases compostas diferentes — o _too_similar não pega (resto muda demais).
AIRPORT_V1 = (
    "Qual aeroporto de São Paulo você prefere: GRU (Guarulhos), CGH (Congonhas) "
    "ou VCP (Campinas)?\nE qual a data de ida (dd/mm)?"
)
AIRPORT_V2 = (
    "Qual aeroporto de São Paulo você prefere: GRU (Guarulhos), CGH (Congonhas) "
    "ou VCP (Campinas)?\nE quantas pessoas vão viajar (adultos e crianças)?"
)
AIRPORT_V3 = (
    "*Qual aeroporto de São Paulo você prefere: GRU (Guarulhos), CGH (Congonhas) "
    "ou VCP (Campinas)?*\nE a forma de pagamento: Pix, boleto ou cartão?"
)


def _hist_fixacao() -> list[dict]:
    """Histórico com a pergunta do aeroporto já feita 2× (a 3ª é fixação)."""
    return [
        {"role": "user", "content": "quero passagem pra Recife"},
        {"role": "assistant", "content": AIRPORT_V1},
        {"role": "user", "content": "dia 20 de dezembro"},
        {"role": "assistant", "content": AIRPORT_V2},
        {"role": "user", "content": "só eu, 1 adulto"},
    ]


def test_question_fixation_pega_terceira_ocorrencia() -> None:
    # O ponto cego do _too_similar: V2 vs V3 mudam o final → abaixo do limiar…
    assert main._too_similar(AIRPORT_V3, AIRPORT_V2) is False
    # …mas a MESMA sub-pergunta na 3ª ocorrência é fixação.
    assert main._question_fixation(AIRPORT_V3, _hist_fixacao()) is True


def test_question_fixation_ignora_segunda_ocorrencia() -> None:
    """Re-perguntar a metade não respondida de uma pergunta composta é follow-up
    legítimo UMA vez — só a 3ª ocorrência conta como fixação."""
    history = [
        {"role": "user", "content": "quero passagem"},
        {"role": "assistant", "content": "Pra onde você quer ir e quando?"},
        {"role": "user", "content": "pra Recife"},
        {"role": "assistant", "content": AIRPORT_V1},
        {"role": "user", "content": "dia 20"},
    ]
    assert main._question_fixation(AIRPORT_V2, history) is False


def test_question_fixation_ignora_perguntas_diferentes() -> None:
    history = _hist_fixacao()
    assert main._question_fixation(ADVANCE, history) is False


def test_questions_of_ignora_cortesia_e_menu() -> None:
    qs = main._questions_of("Tudo bem? 1️⃣ Passagens aéreas\nQual a data de ida da sua viagem?")
    assert qs == ["qual a data de ida da sua viagem?"]


def test_last_assistant_pega_ultima_fala_da_malu() -> None:
    history = [
        {"role": "user", "content": "oi"},
        {"role": "assistant", "content": "primeira"},
        {"role": "user", "content": "quero viajar"},
        {"role": "assistant", "content": "segunda"},
        {"role": "user", "content": "aham"},
    ]
    assert main._last_assistant(history) == "segunda"
    assert main._last_assistant([{"role": "user", "content": "oi"}]) is None


# ---------------------------------------------------------------------------
# Unit — instrução anti-loop injetada no system prompt
# ---------------------------------------------------------------------------
def test_prompt_injeta_bloco_anti_loop() -> None:
    com = _build_system_prompt({"anti_loop": True})
    sem = _build_system_prompt({})
    assert "NÃO repita a pergunta" in com
    assert "NÃO repita a pergunta" not in sem


# ---------------------------------------------------------------------------
# Integração — o pipeline re-prompta e, se persistir, passa pra Lu
# ---------------------------------------------------------------------------
class _FakeDB:
    async def commit(self):  # noqa: ANN001
        return None


class _FakeSession:
    async def __aenter__(self):  # noqa: ANN001
        return _FakeDB()

    async def __aexit__(self, *a):  # noqa: ANN001
        return False


def _base_monkeypatch(monkeypatch, calls, route_fn) -> None:
    """Mocks comuns pros testes de integração do _process_text_message."""

    async def fake_get_state(phone):  # noqa: ANN001
        return ""

    async def fake_get_history(phone):  # noqa: ANN001
        # Última fala da Malu = LOOP_Q → o modelo vai repetir e disparar o anti-loop.
        return [
            {"role": "user", "content": "quero um pacote"},
            {"role": "assistant", "content": LOOP_Q},
        ]

    async def fake_get_or_create(phone, profile, db):  # noqa: ANN001
        return SimpleNamespace(display_name="Rodrigo")

    async def fake_send(to, text):  # noqa: ANN001
        calls["sent"] = text
        return True

    async def fake_save_history(phone, history):  # noqa: ANN001
        calls["saved_last"] = history[-1]["content"]

    async def fake_persist(*a, **k):  # noqa: ANN001, ANN003
        calls.setdefault("persist_models", []).append(a[3] if len(a) > 3 else None)

    async def fake_schedule(phone, name=None):  # noqa: ANN001
        calls["rescheduled"] = True

    async def fake_cancel(phone):  # noqa: ANN001
        calls["cancelled"] = True

    async def fake_set_state(phone, state):  # noqa: ANN001
        calls["state"] = state

    monkeypatch.setattr(main, "get_state", fake_get_state)
    monkeypatch.setattr(main, "get_history", fake_get_history)
    monkeypatch.setattr(main, "SessionLocal", _FakeSession)
    monkeypatch.setattr(main, "get_or_create_cliente", fake_get_or_create)
    monkeypatch.setattr(main, "route_and_ask", route_fn)
    monkeypatch.setattr(main, "send_message", fake_send)
    monkeypatch.setattr(main, "save_history", fake_save_history)
    monkeypatch.setattr(main, "_persist_conversation", fake_persist)
    monkeypatch.setattr(main, "schedule_callbacks", fake_schedule)
    monkeypatch.setattr(main, "cancel_reminders", fake_cancel)
    monkeypatch.setattr(main, "set_state", fake_set_state)


@pytest.mark.asyncio
async def test_reprompt_quebra_o_loop(monkeypatch) -> None:
    """Modelo ia repetir a pergunta → re-prompt com anti_loop → resposta que
    AVANÇA é a que vai pro cliente (não a repetida)."""
    calls: dict[str, object] = {}
    route_calls: list[dict] = []

    async def route_fn(history, customer_context=None):  # noqa: ANN001
        route_calls.append(customer_context or {})
        if customer_context and customer_context.get("anti_loop"):
            return (ADVANCE, "groq/llama")
        return (LOOP_Q, "groq/llama")  # 1ª resposta = repete a última fala

    _base_monkeypatch(monkeypatch, calls, route_fn)

    async def fail_impasse(*a, **k):  # noqa: ANN001, ANN003
        calls["impasse"] = True

    monkeypatch.setattr(main, "_impasse_to_lu", fail_impasse)

    await main._process_text_message("5511900000001", "tenho milhas", "Rodrigo", from_audio=True)

    assert len(route_calls) == 2  # original + re-prompt
    assert route_calls[1].get("anti_loop") is True  # 2ª chamada pediu pra avançar
    assert calls["sent"] == ADVANCE  # foi a resposta que avança, não o loop
    assert "impasse" not in calls  # não precisou passar pra Lu


@pytest.mark.asyncio
async def test_loop_persistente_vira_impasse(monkeypatch) -> None:
    """Mesmo após o re-prompt o modelo repete → impasse (§6): a Lu assume."""
    calls: dict[str, object] = {}

    async def route_fn(history, customer_context=None):  # noqa: ANN001
        return (LOOP_Q, "groq/llama")  # repete SEMPRE, inclusive no re-prompt

    _base_monkeypatch(monkeypatch, calls, route_fn)

    async def fake_notify(phone, name):  # noqa: ANN001
        calls["notified"] = (phone, name)
        return True

    monkeypatch.setattr(main, "notify_luciana_impasse", fake_notify)

    await main._process_text_message("5511900000002", "e as milhas?", "Rodrigo", from_audio=True)

    assert calls["state"] == main.STATE_TRANSFERRED  # Malu silencia
    assert calls["sent"] == main.IMPASSE_REPLY  # mensagem de impasse pro cliente
    assert calls["notified"] == ("5511900000002", "Rodrigo")  # Lu avisada
    assert calls.get("rescheduled") is not True  # não reabre coleta


@pytest.mark.asyncio
async def test_loop_persistente_com_extracao_vira_nudge(monkeypatch) -> None:
    """Refino 2 (05/07): a repetição persiste MAS a extração está viva e sabemos
    o que falta → nudge determinístico pede o mínimo crítico e a coleta segue —
    NÃO derruba na Lu um cliente cooperativo (o caso do aeroporto no S4)."""
    calls: dict[str, object] = {}

    async def route_fn(history, customer_context=None):  # noqa: ANN001
        return (LOOP_Q, "groq/llama")  # repete SEMPRE, inclusive no re-prompt

    _base_monkeypatch(monkeypatch, calls, route_fn)

    async def fake_extract(history):  # noqa: ANN001
        # Datas concretas já dadas; faltam passageiros (+ indicação).
        return {"data_ida": "26/07", "data_volta": "31/07"}

    async def fail_impasse(*a, **k):  # noqa: ANN001, ANN003
        calls["impasse"] = True

    monkeypatch.setattr(main.settings, "coleta_state_enabled", True)
    monkeypatch.setattr(main, "extract_lead_data", fake_extract)
    monkeypatch.setattr(main, "_impasse_to_lu", fail_impasse)

    await main._process_text_message("5511900000004", "tanto faz", "Rodrigo", from_audio=True)

    assert "impasse" not in calls  # Lu NÃO foi acionada
    sent = str(calls["sent"])
    assert "quantas pessoas vão viajar" in sent  # nudge pediu o dado duro
    assert calls.get("rescheduled") is True  # coleta segue aberta (lembrete re-armado)


@pytest.mark.asyncio
async def test_nudge_que_repetiria_vira_impasse(monkeypatch) -> None:
    """Refino 2, trava de segurança: se a última fala da Malu JÁ era o nudge
    determinístico (foi tentado e não avançou), repeti-lo seria loop → aí sim é
    impasse de verdade e a Lu assume."""
    calls: dict[str, object] = {}
    nudge = main.ask_missing_fields(["quantas pessoas vão viajar"])

    async def route_fn(history, customer_context=None):  # noqa: ANN001
        return (nudge, "groq/llama")  # modelo "ecoa" o nudge repetido

    _base_monkeypatch(monkeypatch, calls, route_fn)

    async def fake_get_history(phone):  # noqa: ANN001
        return [
            {"role": "user", "content": "quero um pacote"},
            {"role": "assistant", "content": nudge},  # nudge JÁ foi a última fala
        ]

    async def fake_extract(history):  # noqa: ANN001
        return {"data_ida": "26/07", "data_volta": "31/07"}

    async def fake_notify(phone, name):  # noqa: ANN001
        calls["notified"] = True
        return True

    monkeypatch.setattr(main, "get_history", fake_get_history)
    monkeypatch.setattr(main.settings, "coleta_state_enabled", True)
    monkeypatch.setattr(main, "extract_lead_data", fake_extract)
    monkeypatch.setattr(main, "notify_luciana_impasse", fake_notify)

    await main._process_text_message("5511900000005", "hmm", "Rodrigo", from_audio=True)

    assert calls["state"] == main.STATE_TRANSFERRED
    assert calls["sent"] == main.IMPASSE_REPLY
    assert calls.get("notified") is True


@pytest.mark.asyncio
async def test_fixacao_em_subpergunta_dispara_reprompt(monkeypatch) -> None:
    """Refino 3 (05/07): a resposta NÃO é quase-igual à anterior no todo, mas
    re-faz a MESMA sub-pergunta pela 3ª vez → dispara o re-prompt anti-loop."""
    calls: dict[str, object] = {}
    route_calls: list[dict] = []

    async def route_fn(history, customer_context=None):  # noqa: ANN001
        route_calls.append(customer_context or {})
        if customer_context and customer_context.get("anti_loop"):
            return (ADVANCE, "groq/llama")
        return (AIRPORT_V3, "groq/llama")  # 3ª vez da pergunta do aeroporto

    _base_monkeypatch(monkeypatch, calls, route_fn)

    async def fake_get_history(phone):  # noqa: ANN001
        return _hist_fixacao()[:-1]  # o turno atual do cliente entra no dispatch

    monkeypatch.setattr(main, "get_history", fake_get_history)

    await main._process_text_message("5511900000006", "só eu, 1 adulto", "Rodrigo", from_audio=True)

    assert len(route_calls) == 2  # fixação detectada → re-prompt
    assert route_calls[1].get("anti_loop") is True
    assert calls["sent"] == ADVANCE  # a resposta que avança é a que sai


@pytest.mark.asyncio
async def test_resposta_diferente_nao_dispara_reprompt(monkeypatch) -> None:
    """Resposta normal (não repete) → uma chamada só, sem re-prompt nem impasse."""
    calls: dict[str, object] = {}
    route_calls: list[dict] = []

    async def route_fn(history, customer_context=None):  # noqa: ANN001
        route_calls.append(customer_context or {})
        return (ADVANCE, "groq/llama")  # diferente da última fala (LOOP_Q)

    _base_monkeypatch(monkeypatch, calls, route_fn)

    await main._process_text_message("5511900000003", "oi", "Rodrigo", from_audio=True)

    assert len(route_calls) == 1  # sem re-prompt
    assert calls["sent"] == ADVANCE

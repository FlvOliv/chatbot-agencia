"""Testes da ficha de coleta persistida (resiliência da Alavanca B, 05/07).

A extração de IA morre sob pico/cota (visto ao vivo: Groq 429 → fallback
instável) e sem ela o digest, o nudge e o gate voavam às cegas. A última ficha
BOA fica persistida no Redis (fakeredis no conftest) e assume quando a extração
cai. O fecho determinístico continua exigindo ficha FRESCA (deste turno).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app import main
from app.briefing import normalize_lead_data, render_briefing
from app.session import clear_coleta_state, get_coleta_state, save_coleta_state

# Resposta neutra do modelo — diferente da última fala da Malu (não é loop).
REPLY = "Perfeito! E você prefere cabine interna, externa ou com varanda?"


class _FakeDB:
    async def commit(self):  # noqa: ANN001
        return None


class _FakeSession:
    async def __aenter__(self):  # noqa: ANN001
        return _FakeDB()

    async def __aexit__(self, *a):  # noqa: ANN001
        return False


def _wire(monkeypatch, calls, route_fn) -> None:
    """Mocks mínimos pro _process_text_message (padrão do test_anti_loop)."""

    async def fake_get_state(phone):  # noqa: ANN001
        return ""

    async def fake_get_history(phone):  # noqa: ANN001
        return [
            {"role": "user", "content": "quero um cruzeiro pro nordeste"},
            {"role": "assistant", "content": "Qual porto de embarque você prefere?"},
        ]

    async def fake_get_or_create(phone, profile, db):  # noqa: ANN001
        return SimpleNamespace(display_name="Flávio")

    async def fake_send(to, text):  # noqa: ANN001
        calls["sent"] = text
        return True

    async def fake_save_history(phone, history):  # noqa: ANN001
        pass

    async def fake_persist(*a, **k):  # noqa: ANN001, ANN003
        pass

    async def fake_schedule(phone, name=None):  # noqa: ANN001
        calls["rescheduled"] = True

    async def fake_cancel(phone):  # noqa: ANN001
        pass

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
    monkeypatch.setattr(main.settings, "coleta_state_enabled", True)


@pytest.mark.asyncio
async def test_roundtrip_da_ficha_no_redis() -> None:
    """save/get/clear da ficha — unidade do app/session.py."""
    phone = "5511911110000"
    assert await get_coleta_state(phone) is None
    await save_coleta_state(phone, {"origem": "Santos"})
    assert await get_coleta_state(phone) == {"origem": "Santos"}
    await clear_coleta_state(phone)
    assert await get_coleta_state(phone) is None


@pytest.mark.asyncio
async def test_extracao_ok_salva_ficha_e_injeta_digest(monkeypatch) -> None:
    """Extração viva → ficha normalizada persistida + digest no prompt do turno."""
    calls: dict[str, object] = {}
    contexts: list[dict] = []

    async def route_fn(history, customer_context=None):  # noqa: ANN001
        contexts.append(customer_context or {})
        return (REPLY, "groq/llama")

    _wire(monkeypatch, calls, route_fn)

    async def fake_extract(history):  # noqa: ANN001
        return {"tipo_atendimento": "Cruzeiro", "origem": "Santos", "qtd_adultos": "6"}

    monkeypatch.setattr(main, "extract_lead_data", fake_extract)

    phone = "5511911110001"
    await main._process_text_message(phone, "saindo de santos", "Flávio", from_audio=True)

    ficha = await get_coleta_state(phone)
    assert ficha is not None and ficha["origem"] == "Santos"
    assert "Já informado pelo cliente" in str(contexts[0].get("coleta_state"))


@pytest.mark.asyncio
async def test_extracao_morta_usa_ficha_persistida(monkeypatch) -> None:
    """Extração caiu NESTE turno → o digest vem da ficha persistida: a Malu
    continua sabendo o que o cliente já disse (nada de reperguntar o porto)."""
    calls: dict[str, object] = {}
    contexts: list[dict] = []

    async def route_fn(history, customer_context=None):  # noqa: ANN001
        contexts.append(customer_context or {})
        return (REPLY, "groq/llama")

    _wire(monkeypatch, calls, route_fn)

    async def dead_extract(history):  # noqa: ANN001
        raise RuntimeError("429 em toda a cadeia")

    monkeypatch.setattr(main, "extract_lead_data", dead_extract)

    phone = "5511911110002"
    await save_coleta_state(
        phone,
        normalize_lead_data(
            {"tipo_atendimento": "Cruzeiro", "origem": "Santos", "qtd_adultos": "6"}
        ),
    )

    await main._process_text_message(phone, "cabine interna", "Flávio", from_audio=True)

    digest = str(contexts[0].get("coleta_state"))
    assert "Santos" in digest


@pytest.mark.asyncio
async def test_ficha_persistida_nao_dispara_fecho_deterministico(monkeypatch) -> None:
    """Ficha antiga COMPLETA + extração morta → NÃO fecha sozinho: só ficha
    fresca fecha (a persistida pode estar 1 turno atrás da última fala)."""
    calls: dict[str, object] = {}

    async def route_fn(history, customer_context=None):  # noqa: ANN001
        return (REPLY, "groq/llama")

    _wire(monkeypatch, calls, route_fn)

    async def dead_extract(history):  # noqa: ANN001
        return None

    async def fail_finalize(*a, **k):  # noqa: ANN001, ANN003
        calls["finalized"] = True
        return 1

    monkeypatch.setattr(main, "extract_lead_data", dead_extract)
    monkeypatch.setattr(main, "_finalize_lead", fail_finalize)

    phone = "5511911110003"
    # Ficha sem faltas duras: cruzeiro + período concreto + pax + indicação dada.
    await save_coleta_state(
        phone,
        normalize_lead_data(
            {
                "tipo_atendimento": "Cruzeiro",
                "data_ida": "05/08/2026",
                "qtd_adultos": "6",
                "indicado_por": "Maria",
            }
        ),
    )

    await main._process_text_message(phone, "ok", "Flávio", from_audio=True)

    assert "finalized" not in calls  # fecho automático NÃO disparou
    assert calls["sent"] == REPLY  # a resposta normal do modelo seguiu


@pytest.mark.asyncio
async def test_fecho_com_extracao_morta_usa_bloco_do_modelo(monkeypatch) -> None:
    """Cadeia de IA esgotada no fecho (extração lança) mas o modelo emitiu um
    bloco COMPLETO → o parse determinístico do próprio bloco alimenta o gate e
    o lead FECHA — antes, o gate rodava sobre {} e pedia tudo de novo em loop
    (caso real de 05/07 18:42)."""
    calls: dict[str, object] = {}
    block_data = {
        "tipo_atendimento": "Passagens aéreas",
        "origem": "São Paulo",
        "destino": "Recife",
        "data_ida": "20/12/2030",
        "data_volta": "27/12/2030",
        "qtd_adultos": "2",
        "indicado_por": "Ana",
    }

    async def route_fn(history, customer_context=None):  # noqa: ANN001
        return (
            f"Perfeito, fechado!\n\n{render_briefing(block_data, '5511911110004')}",
            "groq/llama",
        )

    _wire(monkeypatch, calls, route_fn)

    async def dead_extract(history):  # noqa: ANN001
        raise RuntimeError("429 em toda a cadeia")

    async def fake_finalize(phone, history, block, data):  # noqa: ANN001
        calls["finalized_data"] = data
        return 1042

    async def fake_push(*a, **k):  # noqa: ANN001, ANN003
        pass

    monkeypatch.setattr(main, "extract_lead_data", dead_extract)
    monkeypatch.setattr(main, "_finalize_lead", fake_finalize)
    monkeypatch.setattr(main, "send_push_to_all", fake_push)

    await main._process_text_message(
        "5511911110004", "pode fechar", "Flávio", from_audio=True
    )

    data = calls.get("finalized_data")
    assert data is not None and data["data_ida"] == "20/12/2030"  # fechou pelo bloco
    assert calls["state"] == main.STATE_TRANSFERRED  # e silenciou
    assert "Anotei:" in str(calls["sent"])  # recap no fechamento


@pytest.mark.asyncio
async def test_nudge_repetido_no_gate_vira_impasse(monkeypatch) -> None:
    """O nudge do gate não passa pelo anti-loop do modelo: sem esta trava ele
    repetia VERBATIM a cada turno (loop real de 05/07 18:42/18:43). Se o mesmo
    nudge já foi a última fala e o cliente respondeu, não há como validar sem
    extração → a Lu assume (§6)."""
    calls: dict[str, object] = {}
    nudge_prev = main.ask_missing_fields(
        [
            "a data ou o período da viagem",
            "quantas pessoas vão viajar",
        ]
    )

    async def route_fn(history, customer_context=None):  # noqa: ANN001
        return ("Perfeito, vou organizar tudo!\n## Resumo", "groq/llama")

    _wire(monkeypatch, calls, route_fn)

    async def fake_get_history(phone):  # noqa: ANN001
        return [
            {"role": "user", "content": "quero cotar uma viagem"},
            {"role": "assistant", "content": "Alguém indicou a Lu pra você? 💛"},
            {"role": "user", "content": "ninguém"},
            {"role": "assistant", "content": nudge_prev},  # nudge JÁ foi a última fala
        ]

    def fake_split(reply):  # noqa: ANN001
        # Bloco sem campos parseáveis — o parse devolve {} e o gate segue vazio.
        return "Perfeito, vou organizar tudo!", "## Resumo da Solicitação"

    async def dead_extract(history):  # noqa: ANN001
        return None

    async def fake_notify(phone, name):  # noqa: ANN001
        calls["notified"] = True
        return True

    monkeypatch.setattr(main, "get_history", fake_get_history)
    monkeypatch.setattr(main, "split_reply_and_briefing", fake_split)
    monkeypatch.setattr(main, "extract_lead_data", dead_extract)
    monkeypatch.setattr(main, "notify_luciana_impasse", fake_notify)

    await main._process_text_message(
        "5511911110005", "é ida e volta, vou sozinho", "Flávio", from_audio=True
    )

    assert calls["state"] == main.STATE_TRANSFERRED  # Malu silenciou
    assert calls["sent"] == main.IMPASSE_REPLY  # cliente ouviu que a Lu assume
    assert calls.get("notified") is True  # Lu avisada com o contexto

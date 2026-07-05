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
from app.briefing import normalize_lead_data
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

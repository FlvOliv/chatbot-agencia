"""Testes da Alavanca B — estado de coleta injetado (a Malu não repergunta)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app import main
from app.ai import _build_system_prompt
from app.briefing import build_coleta_digest, normalize_lead_data


# ---------------------------------------------------------------------------
# Unit — digest do que já foi coletado
# ---------------------------------------------------------------------------
def test_digest_lista_campos_informados() -> None:
    data = normalize_lead_data(
        {
            "nome_cliente": "Rodrigo",
            "tipo_atendimento": "Passagens aéreas",
            "origem": "São Paulo",
            "destino": "Fortaleza",
            "qtd_adultos": "1",
        }
    )
    d = build_coleta_digest(data, history=[])
    assert d is not None
    assert "Destino: Fortaleza" in d
    assert "Origem: São Paulo" in d
    assert "Passagens aéreas" in d
    assert "Rodrigo" not in d  # nome é identidade → fica fora do digest


def test_digest_none_quando_nada_coletado() -> None:
    assert build_coleta_digest(normalize_lead_data({}), history=[]) is None


def test_digest_ignora_campo_pendente() -> None:
    # "mês que vem" vira "pendente" no normalize → NÃO conta como informado
    # (é genuinamente incompleto e deve ser reperguntado).
    data = normalize_lead_data({"data_ida": "mês que vem", "destino": "Recife"})
    d = build_coleta_digest(data, history=[])
    assert "Recife" in d
    assert "pendente" not in d


def _data_completa() -> dict:
    return normalize_lead_data(
        {
            "origem": "São Paulo",
            "destino": "Recife",
            "data_ida": "20/12",
            "data_volta": "27/12",
            "qtd_adultos": "2",
        }
    )


def test_digest_manda_fechar_quando_tudo_completo() -> None:
    """Refino 1 (05/07): sem faltas duras E indicação tratada → o digest manda
    FECHAR — sem esse sinal o modelo fica em loop de perguntas opcionais."""
    hist = [{"role": "assistant", "content": "Alguém indicou a Lu pra você?"}]
    d = build_coleta_digest(_data_completa(), history=hist)
    assert "FECHE AGORA" in d
    assert "Resumo da Solicitação de Cotação" in d
    assert "Falta o essencial" not in d


def test_digest_pede_so_indicacao_quando_e_o_unico_pendente() -> None:
    # Dados duros completos, mas a Malu nunca perguntou indicação → o digest
    # manda fazer a ÚLTIMA pergunta e já fechar na sequência.
    d = build_coleta_digest(_data_completa(), history=[])
    assert "última pergunta" in d
    assert "indicou" in d
    assert "FECHE AGORA" not in d
    assert "Falta o essencial" not in d


def test_digest_incompleto_nao_manda_fechar() -> None:
    # Regressão: com falta dura o comportamento antigo permanece (lista a falta,
    # nada de sinal de fechamento).
    data = normalize_lead_data({"destino": "Recife", "qtd_adultos": "2"})
    d = build_coleta_digest(data, history=[])
    assert "Falta o essencial" in d
    assert "FECHE" not in d


# ---------------------------------------------------------------------------
# Unit — injeção no system prompt
# ---------------------------------------------------------------------------
def test_prompt_injeta_coleta_state() -> None:
    com = _build_system_prompt(
        {"coleta_state": "Já informado pelo cliente:\n- Destino: Fortaleza"}
    )
    sem = _build_system_prompt({})
    assert "Coleta até agora" in com
    assert "Fortaleza" in com
    assert "Coleta até agora" not in sem


# ---------------------------------------------------------------------------
# Integração — o pipeline extrai 1× e injeta o estado no turno seguinte
# ---------------------------------------------------------------------------
class _FakeDB:
    async def commit(self):  # noqa: ANN001
        return None


class _FakeSession:
    async def __aenter__(self):  # noqa: ANN001
        return _FakeDB()

    async def __aexit__(self, *a):  # noqa: ANN001
        return False


@pytest.mark.asyncio
async def test_process_injeta_coleta_state(monkeypatch) -> None:
    ctxs: list[dict] = []
    calls: dict[str, object] = {}

    async def fake_get_state(phone):  # noqa: ANN001
        return ""

    async def fake_get_history(phone):  # noqa: ANN001
        return [
            {"role": "user", "content": "quero passagem pra Fortaleza"},
            {"role": "assistant", "content": "De qual cidade você sai?"},
        ]

    async def fake_get_or_create(phone, profile, db):  # noqa: ANN001
        return SimpleNamespace(display_name="Rodrigo")

    async def fake_extract(history):  # noqa: ANN001
        calls["extracted"] = True
        return {
            "destino": "Fortaleza",
            "origem": "São Paulo",
            "tipo_atendimento": "Passagens aéreas",
            "qtd_adultos": "1",
        }

    async def fake_route(history, customer_context=None):  # noqa: ANN001
        ctxs.append(customer_context or {})
        return ("Beleza! E quantas pessoas vão viajar?", "groq/llama")

    async def fake_send(to, text):  # noqa: ANN001
        return True

    async def noop(*a, **k):  # noqa: ANN001, ANN003
        return None

    monkeypatch.setattr(main.settings, "coleta_state_enabled", True)
    monkeypatch.setattr(main, "get_state", fake_get_state)
    monkeypatch.setattr(main, "get_history", fake_get_history)
    monkeypatch.setattr(main, "SessionLocal", _FakeSession)
    monkeypatch.setattr(main, "get_or_create_cliente", fake_get_or_create)
    monkeypatch.setattr(main, "extract_lead_data", fake_extract)
    monkeypatch.setattr(main, "route_and_ask", fake_route)
    monkeypatch.setattr(main, "send_message", fake_send)
    monkeypatch.setattr(main, "save_history", noop)
    monkeypatch.setattr(main, "_persist_conversation", noop)
    monkeypatch.setattr(main, "schedule_callbacks", noop)
    monkeypatch.setattr(main, "cancel_reminders", noop)

    await main._process_text_message("5511900000010", "sampa", "Rodrigo", from_audio=True)

    assert calls.get("extracted") is True
    assert ctxs[0].get("coleta_state") is not None
    assert "Fortaleza" in ctxs[0]["coleta_state"]  # já informado → vai no prompt


@pytest.mark.asyncio
async def test_process_fecha_deterministico_quando_gate_completo(monkeypatch) -> None:
    """Refino 05/07: gate COMPLETO + modelo sem `## Resumo` → o código fecha
    sozinho. O fallback (gpt-oss-120b) ignora o "FECHE AGORA" do digest e fica
    em loop de menus opcionais (S3 da suíte de conformidade) — o fecho não pode
    depender da cooperação do modelo."""
    calls: dict[str, object] = {}

    async def fake_get_state(phone):  # noqa: ANN001
        return ""

    async def fake_get_history(phone):  # noqa: ANN001
        return [
            {"role": "user", "content": "quero Paris, ida 10/08 e volta 15/08"},
            {"role": "assistant", "content": "Alguém indicou a Lu pra você?"},
        ]

    async def fake_get_or_create(phone, profile, db):  # noqa: ANN001
        return SimpleNamespace(display_name="Diego")

    async def fake_extract(history):  # noqa: ANN001
        return {
            "origem": "São Paulo",
            "destino": "Paris",
            "data_ida": "10/08",
            "data_volta": "15/08",
            "qtd_adultos": "2",
        }

    async def fake_route(history, customer_context=None):  # noqa: ANN001
        # Modelo ignora o sinal de fechamento e devolve mais um menu.
        return ("*Qual o tipo de atendimento?* 1️⃣ Passagem 2️⃣ Pacote", "cerebras")

    async def fake_finalize(phone, history, briefing_block, data):  # noqa: ANN001
        calls["data"] = data
        calls["block"] = briefing_block
        return 1031

    async def fake_send(to, text):  # noqa: ANN001
        calls.setdefault("sent", []).append(text)
        return True

    async def noop(*a, **k):  # noqa: ANN001, ANN003
        return None

    monkeypatch.setattr(main.settings, "coleta_state_enabled", True)
    monkeypatch.setattr(main, "get_state", fake_get_state)
    monkeypatch.setattr(main, "get_history", fake_get_history)
    monkeypatch.setattr(main, "SessionLocal", _FakeSession)
    monkeypatch.setattr(main, "get_or_create_cliente", fake_get_or_create)
    monkeypatch.setattr(main, "extract_lead_data", fake_extract)
    monkeypatch.setattr(main, "route_and_ask", fake_route)
    monkeypatch.setattr(main, "_finalize_lead", fake_finalize)
    monkeypatch.setattr(main, "send_message", fake_send)
    monkeypatch.setattr(main, "save_history", noop)
    monkeypatch.setattr(main, "_persist_conversation", noop)
    monkeypatch.setattr(main, "schedule_callbacks", noop)
    monkeypatch.setattr(main, "cancel_reminders", noop)
    monkeypatch.setattr(main, "send_push_to_all", noop)
    monkeypatch.setattr(main, "set_state", noop)

    await main._process_text_message("5511900000012", "2 adultos", "Diego", from_audio=True)

    assert calls.get("data") is not None  # finalizou
    assert calls["data"]["destino"] == "Paris"
    assert "## Resumo da Solicitação de Cotação" in calls["block"]
    # O cliente recebe o fechamento padrão (protocolo), não o menu do modelo.
    assert any("1031" in s for s in calls["sent"])


@pytest.mark.asyncio
async def test_process_pula_coleta_state_no_primeiro_turno(monkeypatch) -> None:
    """1º turno: nada coletado ainda → B pulada (sem extração extra)."""
    ctxs: list[dict] = []
    calls: dict[str, object] = {}

    async def fake_get_state(phone):  # noqa: ANN001
        return ""

    async def fake_get_history(phone):  # noqa: ANN001
        return []  # primeiro turno

    async def fake_get_or_create(phone, profile, db):  # noqa: ANN001
        return SimpleNamespace(display_name="Rodrigo")

    async def fake_reserva(phone, db):  # noqa: ANN001
        return False

    async def fake_extract(history):  # noqa: ANN001
        calls["extracted"] = True
        return {"destino": "Fortaleza"}

    async def fake_route(history, customer_context=None):  # noqa: ANN001
        ctxs.append(customer_context or {})
        return ("Olá! Pra onde você quer ir?", "groq/llama")

    async def fake_send(to, text):  # noqa: ANN001
        return True

    async def noop(*a, **k):  # noqa: ANN001, ANN003
        return None

    monkeypatch.setattr(main.settings, "coleta_state_enabled", True)
    monkeypatch.setattr(main, "get_state", fake_get_state)
    monkeypatch.setattr(main, "get_history", fake_get_history)
    monkeypatch.setattr(main, "SessionLocal", _FakeSession)
    monkeypatch.setattr(main, "get_or_create_cliente", fake_get_or_create)
    monkeypatch.setattr(main, "has_reserva_ativa", fake_reserva)
    monkeypatch.setattr(main, "extract_lead_data", fake_extract)
    monkeypatch.setattr(main, "route_and_ask", fake_route)
    monkeypatch.setattr(main, "send_message", fake_send)
    monkeypatch.setattr(main, "save_history", noop)
    monkeypatch.setattr(main, "_persist_conversation", noop)
    monkeypatch.setattr(main, "schedule_callbacks", noop)
    monkeypatch.setattr(main, "cancel_reminders", noop)

    await main._process_text_message("5511900000011", "oi", "Rodrigo", from_audio=True)

    assert "extracted" not in calls  # B pulada no 1º turno
    assert ctxs[0].get("coleta_state") is None

"""Testes do extrator/parser de briefing."""

from __future__ import annotations

import pytest

from app.briefing import (
    NAO_INFORMADO,
    extract_briefing,
    extract_customer_name,
    lead_columns_from_data,
    normalize_temp,
    parse_customer_whatsapp,
    parse_lead_temp,
    render_briefing,
    save_lead,
    split_reply_and_briefing,
    split_reply_and_transfer,
)
from app.models import Lead


class _FakeLeadSession:
    """Sessão falsa que captura os leads inseridos (sem Postgres real)."""

    def __init__(self) -> None:
        self.added: list[Lead] = []

    def add(self, obj: Lead) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        # Simula o banco gerando o número de protocolo (sequência).
        for i, lead in enumerate(self.added):
            if lead.numero is None:
                lead.numero = 1001 + i

    async def refresh(self, obj: Lead) -> None:  # noqa: ARG002
        pass


@pytest.mark.asyncio
async def test_save_lead_insere_nova_cotacao_a_cada_chamada() -> None:
    """Mesmo cliente, 2 cotações → 2 leads distintos (NÃO sobrescreve)."""
    db = _FakeLeadSession()

    lead1 = await save_lead(
        "5511999998888", db, briefing_md="cotação 1", lead_temp="quente", name="Ana"
    )
    lead2 = await save_lead(
        "5511999998888", db, briefing_md="cotação 2", lead_temp="frio", name="Ana"
    )

    assert lead1 is not lead2  # dois objetos distintos
    assert len(db.added) == 2  # inseriu dois — não fez upsert
    assert lead1.briefing_md == "cotação 1"
    assert lead2.briefing_md == "cotação 2"
    assert lead1.numero != lead2.numero  # números de protocolo diferentes


@pytest.mark.asyncio
async def test_save_lead_ignora_campos_opcionais_vazios() -> None:
    """Campos opcionais vazios não viram colunas (ficam None no lead novo)."""
    db = _FakeLeadSession()
    lead = await save_lead(
        "5511999998888", db, briefing_md="b", lead_temp="morno", destination=""
    )
    assert lead.destination is None
    assert lead.phone == "5511999998888"


BRIEFING_SAMPLE = """Perfeito! Já organizei suas informações.

## Resumo da Solicitação de Cotação

**Nome do cliente:** Wana
**WhatsApp:** 5511987654321
**Tipo de atendimento:** Pacote completo
**Origem:** São Paulo
**Destino:** Salvador
**Temperatura do lead:** Quente
**Observações importantes:** cliente quer hospedagem em Itapuã
"""


def test_extract_briefing_finds_block() -> None:
    out = extract_briefing(BRIEFING_SAMPLE)
    assert out is not None
    assert out.startswith("## Resumo da Solicitação")
    assert "Wana" in out
    assert "Itapuã" in out


def test_extract_briefing_returns_none_when_absent() -> None:
    assert extract_briefing("Olá! Tudo bem?") is None
    assert extract_briefing("") is None


@pytest.mark.parametrize(
    "temp_value,expected",
    [
        ("Frio", "frio"),
        ("Morno", "morno"),
        ("Quente", "quente"),
        ("Urgente", "urgente"),
        ("morno para quente", "morno"),
        ("MUITO QUENTE", "quente"),
    ],
)
def test_parse_lead_temp_variants(temp_value: str, expected: str) -> None:
    briefing = f"## Resumo da Solicitação\n**Temperatura do lead:** {temp_value}\n"
    assert parse_lead_temp(briefing) == expected


def test_parse_lead_temp_default_when_missing() -> None:
    briefing = "## Resumo da Solicitação\n**Nome:** X\n"
    assert parse_lead_temp(briefing) == "morno"


def test_parse_customer_whatsapp_finds_value() -> None:
    assert parse_customer_whatsapp(BRIEFING_SAMPLE) == "5511987654321"


def test_parse_customer_whatsapp_returns_none_when_absent() -> None:
    briefing = "## Resumo da Solicitação\n**Nome:** X\n"
    assert parse_customer_whatsapp(briefing) is None
    assert parse_customer_whatsapp("") is None


def test_parse_customer_whatsapp_value_on_next_line() -> None:
    briefing = "## Resumo da Solicitação\n**WhatsApp:**\n5511912345678\n"
    assert parse_customer_whatsapp(briefing) == "5511912345678"


def test_extract_customer_name_finds_real_name() -> None:
    assert extract_customer_name(BRIEFING_SAMPLE) == "Wana"


def test_extract_customer_name_ignores_placeholders() -> None:
    cases = [
        "## Resumo\n**Nome do cliente:** [Aguardando você me informar]\n",
        "## Resumo\n**Nome do cliente:** N/A\n",
        "## Resumo\n**Nome do cliente:** Não informado\n",
        "## Resumo\n**Nome do cliente:** —\n",
    ]
    for briefing in cases:
        assert extract_customer_name(briefing) is None, f"falhou em: {briefing!r}"


def test_extract_customer_name_returns_none_when_field_missing() -> None:
    briefing = "## Resumo\n**Destino:** Cancún\n"
    assert extract_customer_name(briefing) is None
    assert extract_customer_name("") is None


# ---------------------------------------------------------------------------
# Briefing ESTRUTURADO — render / split / colunas / temperatura
# ---------------------------------------------------------------------------
def test_render_briefing_marks_missing_as_nao_informado() -> None:
    """Campo não informado pela IA NUNCA é inventado — vira 'Não informado'."""
    data = {"destino": "Maceió", "nome_cliente": "Ana", "temperatura_lead": "quente"}
    out = render_briefing(data, "5511999998888")
    assert "**Destino:** Maceió" in out
    assert "**Nome do cliente:** Ana" in out
    # os campos que estouravam (pagamento/motivo) agora ficam Não informado
    assert f"**Forma de pagamento:** {NAO_INFORMADO}" in out
    assert f"**Motivo da viagem:** {NAO_INFORMADO}" in out
    assert "**Temperatura do lead:** Quente" in out
    # WhatsApp cai pro número real do webhook quando a IA não capturou
    assert "**WhatsApp:** 5511999998888" in out


def test_render_briefing_treats_placeholders_as_missing() -> None:
    data = {"forma_pagamento": "Não informado", "destino": "—", "origem": "n/a"}
    out = render_briefing(data)
    assert f"**Forma de pagamento:** {NAO_INFORMADO}" in out
    assert f"**Destino:** {NAO_INFORMADO}" in out
    assert f"**Origem:** {NAO_INFORMADO}" in out


def test_render_briefing_defaults_temp_to_morno() -> None:
    assert "**Temperatura do lead:** Morno" in render_briefing({})
    assert "**Temperatura do lead:** Morno" in render_briefing({"temperatura_lead": "xpto"})


def test_lead_columns_from_data_maps_fields() -> None:
    data = {
        "nome_cliente": "Ana",
        "destino": "Maceió",
        "tipo_atendimento": "Pacote completo",
        "temperatura_lead": "urgente",
    }
    assert lead_columns_from_data(data) == {
        "name": "Ana",
        "destination": "Maceió",
        "travel_type": "Pacote completo",
        "lead_temp": "urgente",
    }


def test_lead_columns_nulls_become_none() -> None:
    cols = lead_columns_from_data({"nome_cliente": None, "destino": ""})
    assert cols["name"] is None
    assert cols["destination"] is None
    assert cols["lead_temp"] == "morno"  # default


def test_split_reply_separates_briefing_block() -> None:
    reply = (
        "Perfeito, Ana! Já tenho tudo.\n\n"
        "## Resumo da Solicitação de Cotação\n"
        "**Nome do cliente:** Ana\n"
    )
    customer, block = split_reply_and_briefing(reply)
    assert customer == "Perfeito, Ana! Já tenho tudo."
    assert block is not None and block.startswith("## Resumo da Solicitação")


def test_split_reply_without_block() -> None:
    customer, block = split_reply_and_briefing("Oi! Tudo bem?")
    assert customer == "Oi! Tudo bem?"
    assert block is None


def test_split_reply_ignores_empty_briefing_header() -> None:
    # Modelo escreveu o header no meio da frase, sem os campos → NÃO finaliza
    # (senão vira lead/protocolo espúrio) e o header não vaza pro cliente.
    reply = (
        "Em breve ela entra em contato com o\n\n"
        "## Resumo da Solicitação de Cotação\n"
    )
    customer, block = split_reply_and_briefing(reply)
    assert block is None
    assert "## Resumo" not in customer


def test_split_transfer_detects_marker() -> None:
    reply = "Claro! Já vou chamar a Lu pra te ajudar com isso 🙌\n\n## TRANSFERIR"
    customer, wants = split_reply_and_transfer(reply)
    assert wants is True
    assert "## TRANSFERIR" not in customer
    assert customer == "Claro! Já vou chamar a Lu pra te ajudar com isso 🙌"


def test_split_transfer_case_insensitive() -> None:
    customer, wants = split_reply_and_transfer("Beleza!\n## transferir")
    assert wants is True
    assert customer == "Beleza!"


def test_split_transfer_without_marker() -> None:
    customer, wants = split_reply_and_transfer("Qual a sua cidade de origem?")
    assert wants is False
    assert customer == "Qual a sua cidade de origem?"


def test_split_transfer_empty() -> None:
    customer, wants = split_reply_and_transfer("")
    assert wants is False
    assert customer == ""


def test_normalize_temp_variants() -> None:
    assert normalize_temp("Quente") == "quente"
    assert normalize_temp("muito urgente mesmo") == "urgente"
    assert normalize_temp("xyz") == "morno"
    assert normalize_temp(None) == "morno"


# ---------------------------------------------------------------------------
# Aviso pra Lu — deep link pro painel
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_notify_luciana_includes_panel_link(monkeypatch) -> None:
    from app import briefing as b

    captured: dict[str, str] = {}

    async def fake_send(to, text):  # noqa: ANN001, ARG001
        captured["text"] = text
        return True

    monkeypatch.setattr(b, "send_message", fake_send)
    monkeypatch.setattr(b.settings, "panel_base_url", "https://painel.malu.app")

    await b.notify_luciana(
        "## Resumo da Solicitação de Cotação\n**Temperatura do lead:** Quente\n",
        "5511999998888",
    )
    assert "https://painel.malu.app/conversas/5511999998888" in captured["text"]


@pytest.mark.asyncio
async def test_notify_returning_client_includes_panel_link(monkeypatch) -> None:
    from app import briefing as b

    captured: dict[str, str] = {}

    async def fake_send(to, text):  # noqa: ANN001, ARG001
        captured["text"] = text
        return True

    monkeypatch.setattr(b, "send_message", fake_send)
    monkeypatch.setattr(b.settings, "panel_base_url", "https://painel.malu.app")

    await b.notify_luciana_returning_client("5511977776666", "Ana")
    assert "https://painel.malu.app/conversas/5511977776666" in captured["text"]


@pytest.mark.asyncio
async def test_notify_ai_down_includes_panel_link(monkeypatch) -> None:
    from app import briefing as b

    captured: dict[str, str] = {}

    async def fake_send(to, text):  # noqa: ANN001, ARG001
        captured["text"] = text
        return True

    monkeypatch.setattr(b, "send_message", fake_send)
    monkeypatch.setattr(b.settings, "panel_base_url", "https://painel.malu.app")

    await b.notify_luciana_ai_down("5511955554444", "João")
    assert "https://painel.malu.app/conversas/5511955554444" in captured["text"]
    assert "travou" in captured["text"].lower()

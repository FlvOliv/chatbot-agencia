"""Testes do extrator/parser de briefing."""

from __future__ import annotations

import pytest

from app.briefing import (
    extract_briefing,
    extract_customer_name,
    parse_customer_whatsapp,
    parse_lead_temp,
)


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

"""Testes dos guards de saída — rede de segurança determinística (P0)."""

from __future__ import annotations

import pytest

from app.sanitize import PRICE_SAFE_REPLY, price_guard, sanitize_outgoing


@pytest.mark.parametrize(
    "text",
    [
        "Fica em R$ 900 a passagem.",
        "A passagem custa R$1.200,00.",
        "Sai por 900 reais.",
        "Dá uns 2 mil ida e volta.",
        "Fica em torno de dois mil.",
        "Tenho uma opção de 1.500 pra você.",
        "Sai por 900,00.",
        "A partir de 900 já dá pra viajar.",
    ],
)
def test_price_guard_bloqueia_precos(text: str) -> None:
    """Qualquer menção a valor monetário vira a frase segura + flag de bloqueio."""
    out, blocked = price_guard(text)
    assert blocked is True
    assert out == PRICE_SAFE_REPLY


@pytest.mark.parametrize(
    "text",
    [
        "Você viaja dia 12/11/2026?",
        "Vai com 2 adultos e 1 criança?",
        "As crianças têm 5 e 8 anos?",
        "Seu protocolo é #1001.",
        "Prefere voo das 10h ou das 14h?",
        "Vamos para Recife em julho!",
        "",
    ],
)
def test_price_guard_libera_nao_precos(text: str) -> None:
    """Datas, idades, quantidades e horários NÃO podem ser confundidos com preço."""
    out, blocked = price_guard(text)
    assert blocked is False
    assert out == text


def test_sanitize_converte_negrito_duplo() -> None:
    assert sanitize_outgoing("Olá **João**!") == "Olá *João*!"


def test_sanitize_remove_cabecalho() -> None:
    assert sanitize_outgoing("## Título\nOi") == "Título\nOi"


def test_sanitize_remove_asterisco_orfao() -> None:
    """3 asteriscos (ímpar) = negrito quebrado → remove todos."""
    out = sanitize_outgoing("qual o *destino? E a **cidade*?")
    assert "*" not in out


def test_sanitize_mantem_negrito_balanceado() -> None:
    assert sanitize_outgoing("é *importante* mesmo") == "é *importante* mesmo"


def test_sanitize_texto_vazio() -> None:
    assert sanitize_outgoing("") == ""

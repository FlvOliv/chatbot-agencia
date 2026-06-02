"""Testes dos comandos especiais e parser de intenção (Sprint 1.2 e 1.4)."""

from __future__ import annotations

import pytest

from app.commands import (
    EXIT_REPLY,
    EXIT_WORDS,
    INTENT_NOVA,
    INTENT_RESERVA,
    intent_question,
    intent_unclear_reply,
    is_exit_command,
    parse_intent,
    transferred_reply,
)


@pytest.mark.parametrize(
    "text",
    [
        "sair",
        "/sair",
        "SAIR",
        "Sair",
        "  sair  ",  # com espaços extras
        "parar",
        "/parar",
        "encerrar",
        "tchau",
        "TCHAU",
        "exit",
    ],
)
def test_is_exit_command_matches_keywords(text: str) -> None:
    assert is_exit_command(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "",
        " ",
        "oi",
        "vou sair de casa cedo",  # "sair" no meio de frase → não dispara
        "quero parar pra pensar",
        "ola, é a malu?",
        "preciso sair daqui",
        None,  # type: ignore[arg-type]
    ],
)
def test_is_exit_command_ignores_non_keywords(text) -> None:  # noqa: ANN001
    assert is_exit_command(text) is False


def test_exit_reply_is_warm_and_non_empty() -> None:
    assert EXIT_REPLY
    assert len(EXIT_REPLY) > 20
    # Não soa robótico
    assert "👋" in EXIT_REPLY or "Tudo bem" in EXIT_REPLY


def test_exit_words_set_is_frozen() -> None:
    """Garante que ninguém modifique EXIT_WORDS em runtime por engano."""
    assert isinstance(EXIT_WORDS, frozenset)
    assert "sair" in EXIT_WORDS
    assert "/sair" in EXIT_WORDS


# ---------------------------------------------------------------------------
# parse_intent — cliente com reserva ativa: 1 ou 2?
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text",
    [
        "1",
        " 1 ",
        "1️⃣",
        "um",
        "Primeira",
        "reserva",
        "Tenho",
        "já tenho uma reserva",
        "Tenho uma reserva",
        "MINHA RESERVA",
    ],
)
def test_parse_intent_reserva(text: str) -> None:
    assert parse_intent(text) == INTENT_RESERVA


@pytest.mark.parametrize(
    "text",
    [
        "2",
        " 2 ",
        "2️⃣",
        "dois",
        "Segunda",
        "nova",
        "viagem nova",
        "Quero planejar uma viagem nova",
        "cotar uma nova viagem",
        "procurando uma viagem",
    ],
)
def test_parse_intent_nova(text: str) -> None:
    assert parse_intent(text) == INTENT_NOVA


@pytest.mark.parametrize(
    "text",
    [
        "",
        " ",
        "oi",
        "tudo bem?",
        "talvez",
        "as duas coisas",  # cita as duas — ambíguo
        "tenho reserva mas também quero planejar uma nova",  # menciona ambos
        None,
    ],
)
def test_parse_intent_unclear(text) -> None:  # noqa: ANN001
    assert parse_intent(text) is None


# ---------------------------------------------------------------------------
# Mensagens do fluxo
# ---------------------------------------------------------------------------
def test_intent_question_with_name() -> None:
    msg = intent_question("Maria")
    assert "Maria" in msg
    assert "1️⃣" in msg
    assert "2️⃣" in msg
    assert "reserva" in msg.lower()
    assert "nova" in msg.lower()


def test_intent_question_without_name() -> None:
    msg = intent_question(None)
    assert "Olá!" in msg
    assert "1️⃣" in msg
    assert "2️⃣" in msg


def test_intent_unclear_reply_asks_again() -> None:
    msg = intent_unclear_reply()
    assert "1" in msg and "2" in msg
    assert "reserva" in msg.lower()


def test_transferred_reply_with_name() -> None:
    msg = transferred_reply("João")
    assert "João" in msg
    assert "Lu" in msg


def test_transferred_reply_without_name() -> None:
    msg = transferred_reply(None)
    assert "Lu" in msg
    assert len(msg) > 20

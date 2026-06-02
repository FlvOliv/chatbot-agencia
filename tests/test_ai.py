"""Testes do router de IA multi-provider — usa mocks; não bate em APIs reais.

O conftest.py seta AI_PRIMARY=gemini para os testes. Mockamos
`_ask_provider` (o dispatcher interno) — cobre tanto caminho do primário
quanto do fallback automático adicionado no PR #1.

A assinatura do `_ask_provider` é `(provider, history, system_prompt)`,
e o `route_and_ask` aceita `customer_context` opcional pra injetar contexto
do cliente no system prompt (Sprint 1.3).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app import ai


# ---------------------------------------------------------------------------
# route_and_ask — caminho feliz e erros
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_route_and_ask_uses_primary_when_ok() -> None:
    """Caminho feliz: primário responde, model = nome do primário."""

    async def fake_ask(provider, history, system_prompt):  # noqa: ANN001, ARG001
        return "oi, sou a malu"

    with patch.object(ai, "_ask_provider", side_effect=fake_ask):
        text, model = await ai.route_and_ask(
            [{"role": "user", "content": "oi"}]
        )

    assert text == "oi, sou a malu"
    assert model.startswith("gemini")


@pytest.mark.asyncio
async def test_route_and_ask_returns_error_when_provider_fails(monkeypatch) -> None:
    """Quando todos os providers falham, retorna mensagem padrão e model='error'."""
    monkeypatch.setattr(ai.settings, "ai_fallback", "none")

    async def fake_ask(provider, history, system_prompt):  # noqa: ANN001, ARG001
        raise RuntimeError("provider down")

    with patch.object(ai, "_ask_provider", side_effect=fake_ask):
        text, model = await ai.route_and_ask(
            [{"role": "user", "content": "oi"}]
        )

    assert model == "error"
    assert "probleminha" in text.lower() or "problema" in text.lower()


@pytest.mark.asyncio
async def test_route_and_ask_handles_empty_response(monkeypatch) -> None:
    """Resposta vazia de todos os providers → mensagem de erro suave."""
    monkeypatch.setattr(ai.settings, "ai_fallback", "none")

    async def fake_ask(provider, history, system_prompt):  # noqa: ANN001, ARG001
        return ""

    with patch.object(ai, "_ask_provider", side_effect=fake_ask):
        text, model = await ai.route_and_ask(
            [{"role": "user", "content": "oi"}]
        )

    assert model == "error"
    assert text  # mensagem de erro não-vazia


@pytest.mark.asyncio
async def test_route_and_ask_falls_back_when_primary_fails(monkeypatch) -> None:
    """AI_FALLBACK=auto: primário falha → secundário assume e retorna texto."""
    monkeypatch.setattr(ai.settings, "ai_primary", "gemini")
    monkeypatch.setattr(ai.settings, "ai_fallback", "auto")
    monkeypatch.setattr(ai.settings, "groq_api_key", "test-groq-key")

    chamadas: list[str] = []

    async def fake_ask(provider, history, system_prompt):  # noqa: ANN001, ARG001
        chamadas.append(provider)
        if provider == "gemini":
            raise RuntimeError("gemini com quota estourada")
        return "resposta do groq"

    with patch.object(ai, "_ask_provider", side_effect=fake_ask):
        text, model = await ai.route_and_ask(
            [{"role": "user", "content": "oi"}]
        )

    assert text == "resposta do groq"
    assert model.startswith("llama")
    assert chamadas == ["gemini", "groq"]


@pytest.mark.asyncio
async def test_route_and_ask_explicit_fallback_groq(monkeypatch) -> None:
    """AI_FALLBACK=groq: força fallback no Groq quando primário (Gemini) falha."""
    monkeypatch.setattr(ai.settings, "ai_primary", "gemini")
    monkeypatch.setattr(ai.settings, "ai_fallback", "groq")
    monkeypatch.setattr(ai.settings, "groq_api_key", "test-groq-key")

    async def fake_ask(provider, history, system_prompt):  # noqa: ANN001, ARG001
        if provider == "gemini":
            return ""
        return "resposta do groq"

    with patch.object(ai, "_ask_provider", side_effect=fake_ask):
        text, model = await ai.route_and_ask(
            [{"role": "user", "content": "oi"}]
        )

    assert text == "resposta do groq"
    assert model.startswith("llama")


# ---------------------------------------------------------------------------
# customer_context — Sprint 1.3
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_route_and_ask_passes_customer_name_to_system_prompt() -> None:
    """customer_context.name é injetado no system prompt repassado ao provider."""
    capturado: dict[str, str] = {}

    async def fake_ask(provider, history, system_prompt):  # noqa: ANN001, ARG001
        capturado["sp"] = system_prompt
        return "oi"

    with patch.object(ai, "_ask_provider", side_effect=fake_ask):
        await ai.route_and_ask(
            [{"role": "user", "content": "olá"}],
            customer_context={"name": "Maria", "is_first_turn": True},
        )

    assert "Maria" in capturado["sp"]
    # marcador único da injeção (não aparece no prompt base)
    assert "Contexto do cliente nesta conversa" in capturado["sp"]


@pytest.mark.asyncio
async def test_route_and_ask_without_customer_context_uses_base_prompt() -> None:
    """Sem customer_context, o system prompt é só o base (malu_v4.md)."""
    capturado: dict[str, str] = {}

    async def fake_ask(provider, history, system_prompt):  # noqa: ANN001, ARG001
        capturado["sp"] = system_prompt
        return "oi"

    with patch.object(ai, "_ask_provider", side_effect=fake_ask):
        await ai.route_and_ask([{"role": "user", "content": "oi"}])

    # Não deve conter o bloco de contexto injetado
    assert "Contexto do cliente nesta conversa" not in capturado["sp"]


def test_build_system_prompt_first_turn_inserts_name() -> None:
    """_build_system_prompt na primeira mensagem inclui orientação dedicada."""
    sp = ai._build_system_prompt({"name": "João", "is_first_turn": True})
    assert "João" in sp
    # Variante "primeira mensagem dele nesta sessão" é única da injeção
    assert "primeira mensagem dele nesta sessão" in sp.lower()


def test_build_system_prompt_subsequent_turn() -> None:
    """Em turnos seguintes, NÃO inclui a frase de 'cumprimente agora'."""
    sp = ai._build_system_prompt({"name": "Ana", "is_first_turn": False})
    assert "Ana" in sp
    # A frase usada só no primeiro turno não aparece nos seguintes
    assert "primeira mensagem dele nesta sessão" not in sp.lower()
    # Mas o bloco de contexto ainda aparece com o nome
    assert "Contexto do cliente nesta conversa" in sp


def test_build_system_prompt_empty_context_returns_base() -> None:
    """Sem name, retorna o prompt base sem extras."""
    sp = ai._build_system_prompt(None)
    assert "Contexto do cliente nesta conversa" not in sp


# ---------------------------------------------------------------------------
# Helpers — model_name, fallback resolution
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_active_model_name_follows_ai_primary(monkeypatch) -> None:
    """active_model_name() reflete o provider configurado em AI_PRIMARY."""
    monkeypatch.setattr(ai.settings, "ai_primary", "gemini")
    assert ai.active_model_name() == ai.settings.gemini_model

    monkeypatch.setattr(ai.settings, "ai_primary", "groq")
    assert ai.active_model_name() == ai.settings.groq_model


def test_resolve_fallback_none_returns_none(monkeypatch) -> None:
    monkeypatch.setattr(ai.settings, "ai_fallback", "none")
    assert ai._resolve_fallback("gemini") is None
    assert ai._resolve_fallback("groq") is None


def test_resolve_fallback_auto_picks_opposite(monkeypatch) -> None:
    monkeypatch.setattr(ai.settings, "ai_fallback", "auto")
    monkeypatch.setattr(ai.settings, "gemini_api_key", "k1")
    monkeypatch.setattr(ai.settings, "groq_api_key", "k2")
    assert ai._resolve_fallback("gemini") == "groq"
    assert ai._resolve_fallback("groq") == "gemini"


def test_resolve_fallback_skips_when_no_credential(monkeypatch) -> None:
    monkeypatch.setattr(ai.settings, "ai_fallback", "groq")
    monkeypatch.setattr(ai.settings, "groq_api_key", "")
    assert ai._resolve_fallback("gemini") is None

"""Testes do router de IA multi-provider — usa mocks; não bate em APIs reais.

O conftest.py seta AI_PRIMARY=gemini para os testes. O caminho feliz
verifica que `route_and_ask` retorna o nome do modelo do provider ativo.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app import ai


@pytest.mark.asyncio
async def test_route_and_ask_uses_active_provider_when_ok() -> None:
    """Caminho feliz: ask_malu retorna texto, model = ativo."""

    async def fake_ask(history):  # noqa: ANN001, ARG001
        return "oi, sou a malu"

    with patch.object(ai, "ask_malu", side_effect=fake_ask):
        text, model = await ai.route_and_ask(
            [{"role": "user", "content": "oi"}]
        )

    assert text == "oi, sou a malu"
    # Em testes AI_PRIMARY=gemini → modelo começa com "gemini"
    assert model.startswith("gemini")


@pytest.mark.asyncio
async def test_route_and_ask_returns_error_when_provider_fails() -> None:
    """Quando o provider explode, retornamos mensagem padrão e model='error'."""

    async def fake_ask(history):  # noqa: ANN001, ARG001
        raise RuntimeError("provider down")

    with patch.object(ai, "ask_malu", side_effect=fake_ask):
        text, model = await ai.route_and_ask(
            [{"role": "user", "content": "oi"}]
        )

    assert model == "error"
    assert "probleminha" in text.lower() or "problema" in text.lower()


@pytest.mark.asyncio
async def test_route_and_ask_handles_empty_response() -> None:
    """Resposta vazia do provider → mensagem de erro suave."""

    async def fake_ask(history):  # noqa: ANN001, ARG001
        return ""

    with patch.object(ai, "ask_malu", side_effect=fake_ask):
        text, model = await ai.route_and_ask(
            [{"role": "user", "content": "oi"}]
        )

    assert model == "error"
    assert text  # mensagem de erro não-vazia


@pytest.mark.asyncio
async def test_active_model_name_follows_ai_primary(monkeypatch) -> None:
    """active_model_name() reflete o provider configurado em AI_PRIMARY."""
    from app.config import settings

    # Quando AI_PRIMARY=gemini, retorna o modelo Gemini
    monkeypatch.setattr(settings, "ai_primary", "gemini")
    assert ai.active_model_name() == settings.gemini_model

    # Quando AI_PRIMARY=groq, retorna o modelo Groq
    monkeypatch.setattr(settings, "ai_primary", "groq")
    assert ai.active_model_name() == settings.groq_model

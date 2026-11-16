"""Resposta de chat cortada no teto de tokens nunca vai pro cliente.

Origem: eval de 16/11/2026. O gpt-oss-120b gastou 958 dos 1024 tokens do chat
raciocinando, e a fala saiu "…2 adultos, hotel". Agora modelo de raciocínio tem
teto maior, e `finish_reason == "length"` no chat vira erro (→ próxima perna).
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import respx
from httpx import Response

from app import ai, budget

HIST = [{"role": "user", "content": "oi"}]


def _groq_response(text: str, finish_reason: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text), finish_reason=finish_reason)],
        usage=None,
    )


def _fake_groq_client(response: SimpleNamespace) -> SimpleNamespace:
    create = AsyncMock(return_value=response)
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


# ----------------------------------------------------------------- tetos --
def test_teto_do_chat_maior_so_pra_modelo_de_raciocinio():
    assert ai._max_tokens("openai/gpt-oss-120b", json_mode=False) == ai._MAX_TOKENS_REASONING
    assert ai._max_tokens("gpt-oss-120b", json_mode=False) == ai._MAX_TOKENS_REASONING
    assert ai._max_tokens("llama-3.3-70b-versatile", json_mode=False) == ai._MAX_TOKENS
    assert ai._max_tokens("open-mistral-nemo", json_mode=False) == ai._MAX_TOKENS
    # extração continua com o teto próprio
    assert ai._max_tokens("openai/gpt-oss-120b", json_mode=True) == ai._MAX_TOKENS_EXTRACT
    assert ai._MAX_TOKENS_REASONING > ai._MAX_TOKENS


# ------------------------------------------------------------------ groq --
@pytest.mark.asyncio
async def test_groq_manda_teto_de_raciocinio_pro_gpt_oss():
    client = _fake_groq_client(_groq_response("Oi! Pra onde vamos?", "stop"))
    with patch.object(ai, "_groq_client", return_value=client):
        text = await ai._ask_malu_groq(HIST, "sys", model="openai/gpt-oss-120b")
    assert text == "Oi! Pra onde vamos?"
    assert client.chat.completions.create.call_args.kwargs["max_tokens"] == ai._MAX_TOKENS_REASONING


@pytest.mark.asyncio
async def test_groq_chat_cortado_levanta_erro():
    client = _fake_groq_client(_groq_response("…2 adultos, hotel", "length"))
    with patch.object(ai, "_groq_client", return_value=client):
        with pytest.raises(ai.TruncatedReplyError):
            await ai._ask_malu_groq(HIST, "sys", model="openai/gpt-oss-120b")


@pytest.mark.asyncio
async def test_groq_extracao_cortada_nao_levanta():
    """Na extração o JSON truncado já falha no parse; o caminho fica como era."""
    client = _fake_groq_client(_groq_response('{"destino": "Lis', "length"))
    with patch.object(ai, "_groq_client", return_value=client):
        raw = await ai._ask_malu_groq(HIST, "sys", json_mode=True, model="openai/gpt-oss-120b")
    assert raw == '{"destino": "Lis'


# -------------------------------------------------------- openai-compat --
def _compat_body(text: str, finish_reason: str) -> dict:
    return {
        "choices": [{"message": {"content": text}, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 1024, "total_tokens": 1034},
    }


@pytest.mark.asyncio
@respx.mock
async def test_cerebras_gpt_oss_usa_teto_de_raciocinio_e_corte_vira_erro(monkeypatch):
    monkeypatch.setattr(ai.settings, "cerebras_api_key", "ck")
    monkeypatch.setattr(ai.settings, "cerebras_base_url", "https://api.cerebras.ai/v1")
    monkeypatch.setattr(ai.settings, "cerebras_model", "gpt-oss-120b")
    route = respx.post("https://api.cerebras.ai/v1/chat/completions").mock(
        return_value=Response(200, json=_compat_body("…2 adultos, hotel", "length"))
    )
    with pytest.raises(ai.TruncatedReplyError):
        await ai._ask_malu_cerebras(HIST, "sys")
    assert json.loads(route.calls.last.request.content)["max_tokens"] == ai._MAX_TOKENS_REASONING


@pytest.mark.asyncio
@respx.mock
async def test_mistral_cortado_ainda_conta_tokens_na_trava(monkeypatch):
    monkeypatch.setattr(ai.settings, "mistral_api_key", "mk")
    monkeypatch.setattr(ai.settings, "mistral_base_url", "https://api.mistral.ai/v1")
    monkeypatch.setattr(ai.settings, "paid_floor_model", "open-mistral-nemo")
    respx.post("https://api.mistral.ai/v1/chat/completions").mock(
        return_value=Response(200, json=_compat_body("texto cort", "length"))
    )
    with pytest.raises(ai.TruncatedReplyError):
        await ai._ask_malu_mistral(HIST, "sys")
    assert await budget.paid_tokens_used() == 1034


# -------------------------------------------------------------- cadeia --
@pytest.mark.asyncio
async def test_route_and_ask_pula_perna_cortada(monkeypatch):
    """Primária cortou → a próxima perna responde; o cliente nunca vê o corte."""
    monkeypatch.setattr(ai.settings, "ai_primary", "groq")
    monkeypatch.setattr(ai.settings, "groq_model", "openai/gpt-oss-120b")
    monkeypatch.setattr(ai.settings, "groq_fallback_model", "")
    monkeypatch.setattr(ai.settings, "ai_fallback", "gemini")
    monkeypatch.setattr(ai.settings, "gemini_api_key", "gk")

    async def fake_ask(provider, history, system_prompt, json_mode=False, model=None):  # noqa: ANN001, ARG001
        if provider == "groq":
            raise ai.TruncatedReplyError("groq/openai/gpt-oss-120b: finish_reason=length")
        return "resposta inteira do gemini"

    with patch.object(ai, "_ask_provider", side_effect=fake_ask):
        text, model = await ai.route_and_ask(HIST)
    assert text == "resposta inteira do gemini"
    assert model.startswith("gemini")

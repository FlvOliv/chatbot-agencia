"""Testes do router de IA multi-provider — usa mocks; não bate em APIs reais.

O conftest.py seta AI_PRIMARY=gemini para os testes. Mockamos
`_ask_provider` (o dispatcher interno) — cobre tanto caminho do primário
quanto do fallback automático adicionado no PR #1.

A assinatura do `_ask_provider` é `(provider, history, system_prompt, model=None)`
(o `model` opcional foi adicionado na reserva de modelo do Groq — Fase 1B),
e o `route_and_ask` aceita `customer_context` opcional pra injetar contexto
do cliente no system prompt (Sprint 1.3).
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
import respx
from httpx import Response

from app import ai, budget


# ---------------------------------------------------------------------------
# route_and_ask — caminho feliz e erros
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_route_and_ask_uses_primary_when_ok() -> None:
    """Caminho feliz: primário responde, model = nome do primário."""

    async def fake_ask(provider, history, system_prompt, model=None):  # noqa: ANN001, ARG001
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

    async def fake_ask(provider, history, system_prompt, model=None):  # noqa: ANN001, ARG001
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

    async def fake_ask(provider, history, system_prompt, model=None):  # noqa: ANN001, ARG001
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

    async def fake_ask(provider, history, system_prompt, model=None):  # noqa: ANN001, ARG001
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

    async def fake_ask(provider, history, system_prompt, model=None):  # noqa: ANN001, ARG001
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
# Fase 1B — reserva de MODELO dentro do Groq (não depende do Gemini)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_route_and_ask_uses_groq_fallback_model(monkeypatch) -> None:
    """Modelo principal do Groq falha → 2º modelo do Groq assume sozinho."""
    monkeypatch.setattr(ai.settings, "ai_primary", "groq")
    monkeypatch.setattr(ai.settings, "ai_fallback", "none")
    monkeypatch.setattr(ai.settings, "groq_model", "llama-3.3-70b-versatile")
    monkeypatch.setattr(ai.settings, "groq_fallback_model", "llama-3.1-8b-instant")

    tentativas: list[str | None] = []

    async def fake_ask(provider, history, system_prompt, model=None):  # noqa: ANN001, ARG001
        tentativas.append(model)
        if model == "llama-3.3-70b-versatile":
            raise RuntimeError("429 rate limit")
        return "resposta do modelo leve"

    with patch.object(ai, "_ask_provider", side_effect=fake_ask):
        text, model = await ai.route_and_ask([{"role": "user", "content": "oi"}])

    assert text == "resposta do modelo leve"
    assert model == "llama-3.1-8b-instant"
    assert tentativas == ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]


def test_build_attempts_groq_includes_fallback_model(monkeypatch) -> None:
    """A fila do Groq tem o modelo principal e depois o de reserva."""
    monkeypatch.setattr(ai.settings, "ai_primary", "groq")
    monkeypatch.setattr(ai.settings, "ai_fallback", "none")
    monkeypatch.setattr(ai.settings, "groq_model", "big")
    monkeypatch.setattr(ai.settings, "groq_fallback_model", "small")

    assert ai._build_attempts() == [("groq", "big"), ("groq", "small")]


def test_build_attempts_dedups_when_fallback_equals_primary(monkeypatch) -> None:
    """Reserva igual ao principal não duplica a tentativa."""
    monkeypatch.setattr(ai.settings, "ai_primary", "groq")
    monkeypatch.setattr(ai.settings, "ai_fallback", "none")
    monkeypatch.setattr(ai.settings, "groq_model", "same")
    monkeypatch.setattr(ai.settings, "groq_fallback_model", "same")

    assert ai._build_attempts() == [("groq", "same")]


# ---------------------------------------------------------------------------
# customer_context — Sprint 1.3
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_route_and_ask_passes_customer_name_to_system_prompt() -> None:
    """customer_context.name é injetado no system prompt repassado ao provider."""
    capturado: dict[str, str] = {}

    async def fake_ask(provider, history, system_prompt, model=None):  # noqa: ANN001, ARG001
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

    async def fake_ask(provider, history, system_prompt, model=None):  # noqa: ANN001, ARG001
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


# ---------------------------------------------------------------------------
# extract_lead_data — extração ESTRUTURADA em JSON (substitui o regex)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_extract_lead_data_parses_json(monkeypatch) -> None:
    monkeypatch.setattr(ai.settings, "ai_fallback", "none")
    payload = '{"destino": "Maceió", "forma_pagamento": null, "temperatura_lead": "quente"}'

    async def fake_ask(provider, history, system_prompt, json_mode=False):  # noqa: ANN001, ARG001
        assert json_mode is True  # extração SEMPRE em modo JSON
        return payload

    with patch.object(ai, "_ask_provider", side_effect=fake_ask):
        data = await ai.extract_lead_data(
            [{"role": "user", "content": "quero ir pra maceió"}]
        )

    assert data["destino"] == "Maceió"
    assert data["forma_pagamento"] is None  # null preservado (não inventa)
    assert data["temperatura_lead"] == "quente"


@pytest.mark.asyncio
async def test_extract_lead_data_tolerates_code_fences(monkeypatch) -> None:
    monkeypatch.setattr(ai.settings, "ai_fallback", "none")

    async def fake_ask(provider, history, system_prompt, json_mode=False):  # noqa: ANN001, ARG001
        return '```json\n{"destino": "Salvador"}\n```'

    with patch.object(ai, "_ask_provider", side_effect=fake_ask):
        data = await ai.extract_lead_data([{"role": "user", "content": "x"}])

    assert data == {"destino": "Salvador"}


@pytest.mark.asyncio
async def test_extract_lead_data_returns_none_on_garbage(monkeypatch) -> None:
    monkeypatch.setattr(ai.settings, "ai_fallback", "none")

    async def fake_ask(provider, history, system_prompt, json_mode=False):  # noqa: ANN001, ARG001
        return "isso não é json nenhum"

    with patch.object(ai, "_ask_provider", side_effect=fake_ask):
        data = await ai.extract_lead_data([{"role": "user", "content": "x"}])

    assert data is None  # chamador cai pro fallback regex


@pytest.mark.asyncio
async def test_extract_lead_data_falls_back_provider(monkeypatch) -> None:
    """Primário falha → tenta o reserva (mesma lógica do chat)."""
    monkeypatch.setattr(ai.settings, "ai_primary", "gemini")
    monkeypatch.setattr(ai.settings, "ai_fallback", "auto")
    monkeypatch.setattr(ai.settings, "groq_api_key", "k")
    chamadas: list[str] = []

    async def fake_ask(provider, history, system_prompt, json_mode=False):  # noqa: ANN001, ARG001
        chamadas.append(provider)
        if provider == "gemini":
            raise RuntimeError("quota estourada")
        return '{"destino": "Recife"}'

    with patch.object(ai, "_ask_provider", side_effect=fake_ask):
        data = await ai.extract_lead_data([{"role": "user", "content": "x"}])

    assert data == {"destino": "Recife"}
    assert chamadas == ["gemini", "groq"]


def test_parse_json_object_handles_surrounding_text() -> None:
    assert ai._parse_json_object('Aqui está: {"a": 1} pronto') == {"a": 1}
    assert ai._parse_json_object("") is None
    assert ai._parse_json_object("nada de json") is None


def test_render_transcript_flattens_history() -> None:
    t = ai._render_transcript(
        [
            {"role": "user", "content": "oi"},
            {"role": "assistant", "content": "olá!"},
            {"role": "system", "content": "ignorar"},
        ]
    )
    assert "Cliente: oi" in t
    assert "Malu: olá!" in t
    assert "ignorar" not in t


# ---------------------------------------------------------------------------
# PISO PAGO = Mistral — nova cadeia, trava de orçamento e rótulos
# ---------------------------------------------------------------------------
def _enable_full_chain(monkeypatch, *, paid: bool = True) -> None:
    """Liga a cadeia completa: groq/70b → groq/8b → cerebras → mistral → gemini."""
    monkeypatch.setattr(ai.settings, "ai_primary", "groq")
    monkeypatch.setattr(ai.settings, "ai_fallback", "gemini")
    monkeypatch.setattr(ai.settings, "groq_api_key", "gk")
    monkeypatch.setattr(ai.settings, "groq_model", "groq-70b")
    monkeypatch.setattr(ai.settings, "groq_fallback_model", "groq-8b")
    monkeypatch.setattr(ai.settings, "cerebras_api_key", "ck")
    monkeypatch.setattr(ai.settings, "cerebras_model", "cb-70b")
    monkeypatch.setattr(ai.settings, "mistral_api_key", "mk")
    monkeypatch.setattr(ai.settings, "paid_floor_model", "open-mistral-nemo")
    monkeypatch.setattr(ai.settings, "paid_floor_enabled", paid)
    monkeypatch.setattr(ai.settings, "gemini_api_key", "gemk")


def test_build_attempts_full_chain_order(monkeypatch) -> None:
    """Cadeia na ordem aprovada quando todas as pernas têm credencial."""
    _enable_full_chain(monkeypatch)
    assert ai._build_attempts() == [
        ("groq", "groq-70b"),
        ("groq", "groq-8b"),
        ("cerebras", "cb-70b"),
        ("mistral", "open-mistral-nemo"),
        ("gemini", ai.settings.gemini_model),
    ]


def test_build_attempts_omits_paid_floor_when_disabled(monkeypatch) -> None:
    """PAID_FLOOR_ENABLED=false remove o Mistral, mas mantém o Cerebras grátis."""
    _enable_full_chain(monkeypatch, paid=False)
    attempts = ai._build_attempts()
    assert ("mistral", "open-mistral-nemo") not in attempts
    assert ("cerebras", "cb-70b") in attempts


def test_build_attempts_omits_paid_floor_without_key(monkeypatch) -> None:
    """Sem MISTRAL_API_KEY o piso pago é pulado mesmo com a flag ligada."""
    _enable_full_chain(monkeypatch)
    monkeypatch.setattr(ai.settings, "mistral_api_key", "")
    assert all(p != "mistral" for p, _ in ai._build_attempts())


def test_build_attempts_omits_cerebras_without_key(monkeypatch) -> None:
    """Sem CEREBRAS_API_KEY a perna grátis extra é pulada."""
    _enable_full_chain(monkeypatch)
    monkeypatch.setattr(ai.settings, "cerebras_api_key", "")
    assert all(p != "cerebras" for p, _ in ai._build_attempts())


@pytest.mark.asyncio
async def test_route_and_ask_reaches_mistral_after_free_legs_fail(monkeypatch) -> None:
    """Mistral só é chamado depois de groq/70b, groq/8b e cerebras falharem."""
    _enable_full_chain(monkeypatch)

    ordem: list[str] = []

    async def fake_ask(provider, history, system_prompt, model=None):  # noqa: ANN001, ARG001
        ordem.append(provider)
        if provider in ("groq", "cerebras"):
            raise RuntimeError("perna grátis falhou")
        return "resposta do mistral"

    with patch.object(ai, "_ask_provider", side_effect=fake_ask):
        text, model = await ai.route_and_ask([{"role": "user", "content": "oi"}])

    assert text == "resposta do mistral"
    assert model == "mistral/open-mistral-nemo"  # rótulo prefixado
    assert ordem == ["groq", "groq", "cerebras", "mistral"]


@pytest.mark.asyncio
async def test_route_and_ask_skips_mistral_when_cap_reached(monkeypatch) -> None:
    """Teto mensal estourado → Mistral PULADO → segue pro Gemini."""
    _enable_full_chain(monkeypatch)
    monkeypatch.setattr(ai.settings, "monthly_paid_token_cap", 100)
    await budget.record_paid_tokens(200)  # passa do teto

    ordem: list[str] = []

    async def fake_ask(provider, history, system_prompt, model=None):  # noqa: ANN001, ARG001
        ordem.append(provider)
        if provider == "mistral":
            raise AssertionError("Mistral não deveria ser chamado com teto atingido")
        if provider in ("groq", "cerebras"):
            raise RuntimeError("perna grátis falhou")
        return "resposta do gemini"

    with patch.object(ai, "_ask_provider", side_effect=fake_ask):
        text, model = await ai.route_and_ask([{"role": "user", "content": "oi"}])

    assert text == "resposta do gemini"
    assert model.startswith("gemini")
    assert "mistral" not in ordem
    assert ordem == ["groq", "groq", "cerebras", "gemini"]


@pytest.mark.asyncio
async def test_route_and_ask_labels_cerebras(monkeypatch) -> None:
    """Cerebras que responde é gravado como 'cerebras/<modelo>' (não vira groq)."""
    _enable_full_chain(monkeypatch, paid=False)
    monkeypatch.setattr(ai.settings, "ai_fallback", "none")

    async def fake_ask(provider, history, system_prompt, model=None):  # noqa: ANN001, ARG001
        if provider == "groq":
            raise RuntimeError("groq caiu")
        return "resposta do cerebras"

    with patch.object(ai, "_ask_provider", side_effect=fake_ask):
        text, model = await ai.route_and_ask([{"role": "user", "content": "oi"}])

    assert text == "resposta do cerebras"
    assert model == "cerebras/cb-70b"


@pytest.mark.asyncio
@respx.mock
async def test_mistral_caller_hits_right_url_and_records_tokens(monkeypatch) -> None:
    """O caller do Mistral bate na base_url/modelo certos e contabiliza tokens."""
    monkeypatch.setattr(ai.settings, "mistral_api_key", "mk-secret")
    monkeypatch.setattr(ai.settings, "mistral_base_url", "https://api.mistral.ai/v1")
    monkeypatch.setattr(ai.settings, "paid_floor_model", "open-mistral-nemo")

    route = respx.post("https://api.mistral.ai/v1/chat/completions").mock(
        return_value=Response(
            200,
            json={
                "choices": [{"message": {"content": "olá do mistral"}}],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                },
            },
        )
    )

    text = await ai._ask_malu_mistral(
        [{"role": "user", "content": "oi"}], "system prompt da malu"
    )

    assert text == "olá do mistral"
    assert route.called
    sent = route.calls.last.request
    assert sent.headers["authorization"] == "Bearer mk-secret"
    body = json.loads(sent.content)
    assert body["model"] == "open-mistral-nemo"
    # tokens do piso pago entram na trava de orçamento
    assert await budget.paid_tokens_used() == 15

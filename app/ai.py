"""Router de IA multi-provider — Gemini (primário) ou Groq (stand-by).

A escolha do provider é feita em runtime via `settings.ai_primary`:
    AI_PRIMARY=gemini   → usa Google Gemini (AI Studio)
    AI_PRIMARY=groq     → usa Groq (Llama 3.3 70B)

Trocar de provider é só mudar a variável no `.env` e reiniciar a aplicação.
O system prompt da Malu (`app/prompts/malu_v4.md`) é o mesmo nos dois casos.

Customer context:
    `route_and_ask` aceita opcionalmente um `customer_context` (dict) que é
    injetado dinamicamente no system prompt — útil pra passar o nome do
    cliente capturado da Meta sem mexer no arquivo do prompt.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import google.generativeai as genai
import httpx
from groq import AsyncGroq

from app import budget
from app.config import settings
from app.tenant import get_current_tenant

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent / "prompts" / "malu_v4.md"

# Limite conservador — respostas longas demais ficam ruins no WhatsApp
_MAX_TOKENS = 1024


# ---------------------------------------------------------------------------
# Instrumentação de consumo (só medição — não altera comportamento)
# ---------------------------------------------------------------------------
def _log_usage(provider: str, model: str, usage: Any, json_mode: bool = False) -> None:
    """Loga os tokens de uma chamada, normalizando os dois SDKs.

    Groq (estilo OpenAI): prompt_tokens / completion_tokens / total_tokens,
        cache em prompt_tokens_details.cached_tokens.
    Gemini: prompt_token_count / candidates_token_count / total_token_count,
        cache em cached_content_token_count.

    Nunca levanta — instrumentação não pode derrubar o caminho da resposta.
    """
    if usage is None:
        return
    try:
        prompt = getattr(usage, "prompt_tokens", None)
        if prompt is None:
            prompt = getattr(usage, "prompt_token_count", 0)
        completion = getattr(usage, "completion_tokens", None)
        if completion is None:
            completion = getattr(usage, "candidates_token_count", 0)
        total = getattr(usage, "total_tokens", None)
        if total is None:
            total = getattr(usage, "total_token_count", 0)
        cached = 0
        details = getattr(usage, "prompt_tokens_details", None)
        if details is not None:
            cached = getattr(details, "cached_tokens", 0) or 0
        if not cached:
            cached = getattr(usage, "cached_content_token_count", 0) or 0
        kind = "extract" if json_mode else "chat"
        logger.info(
            "[ai.usage] %s/%s kind=%s prompt=%s completion=%s total=%s cached=%s",
            provider, model, kind, prompt, completion, total, cached,
        )
    except Exception:
        logger.debug("falha ao logar usage de %s/%s", provider, model, exc_info=True)


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _load_system_prompt() -> str:
    """Carrega o system prompt base da Malu (cached em memória)."""
    if not PROMPT_PATH.exists():
        raise FileNotFoundError(
            f"system prompt da Malu não encontrado em {PROMPT_PATH}"
        )
    return PROMPT_PATH.read_text(encoding="utf-8")


_WEEKDAYS_PT = (
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
)


def _today_block() -> str:
    """Âncora temporal — injeta a data de hoje pro modelo resolver datas
    relativas ('amanhã', 'semana que vem') sem inventar nem vazar placeholder."""
    now = datetime.now(ZoneInfo(settings.callback_timezone))
    amanha = now + timedelta(days=1)
    dia = _WEEKDAYS_PT[now.weekday()]
    return (
        "\n\n## Data de hoje (âncora — use SEMPRE)\n"
        f"Hoje é **{dia}, {now:%d/%m/%Y}** (horário de Brasília). "
        f'"Amanhã" = **{amanha:%d/%m/%Y}**. '
        "Resolva qualquer data relativa a partir de hoje; se o cliente disser só "
        "dia/mês, assuma a próxima ocorrência no calendário. NUNCA invente data "
        'nem escreva placeholder do tipo "[data de amanhã]" — calcule.'
    )


def _build_system_prompt(customer_context: dict[str, Any] | None) -> str:
    """Monta o system prompt da chamada atual — base + contexto dinâmico.

    `customer_context` aceita:
        - "name": str → nome do cliente (do profile WhatsApp ou confirmado)
        - "is_first_turn": bool → True na primeira mensagem da sessão
        - "from_audio": bool → True se a mensagem veio de um áudio transcrito
    """
    base = _load_system_prompt()
    extras: list[str] = [_today_block()]

    name = customer_context.get("name") if customer_context else None
    if name:
        is_first = bool(customer_context.get("is_first_turn"))
        if is_first:
            extras.append(
                f"\n\n## Contexto do cliente nesta conversa\n"
                f"O cliente se identifica no WhatsApp como **{name}**.\n"
                f"Esta é a **primeira mensagem dele nesta sessão** — abra com uma "
                f"saudação **calorosa e acolhedora**, chamando-o por **{name}** de "
                f"forma natural, **apresente-se como a Malu** (assistente da Lu) com "
                f"simpatia genuína e um toque afetivo (ex.: 💛) — boas-vindas de "
                f"verdade, nunca uma abertura seca/transacional. No **mesmo turno**, "
                f"já comece o fluxo de coleta. Não peça pra confirmar o nome de forma "
                f"isolada; se ele preferir outro nome, ele vai te avisar."
            )
        else:
            extras.append(
                f"\n\n## Contexto do cliente nesta conversa\n"
                f"O cliente atende por **{name}**. Continue chamando-o pelo "
                f"nome quando fizer sentido no fluxo natural."
            )

    # Ajustes de prompt por agência (B4): texto livre anexado à base (tom, regras
    # da marca). Sem tenant / sem override → nada muda (a Lu usa a base pura).
    tenant = get_current_tenant()
    if tenant is not None and tenant.prompt_overrides:
        system_extra = tenant.prompt_overrides.get("system_extra")
        if system_extra:
            extras.append(f"\n\n## Ajustes da agência\n{system_extra}")

    if customer_context and customer_context.get("from_audio"):
        extras.append(
            "\n\n## Esta mensagem veio de um ÁUDIO transcrito\n"
            "O cliente mandou um áudio que foi transcrito automaticamente — pode "
            "ter pequenos erros (nomes, datas, números). Antes de seguir, "
            "**confirme em 1 linha, de forma leve e natural, o que você "
            'entendeu** (ex.: "Só pra confirmar: você quer ir pra Bariloche em '
            'julho, certo?") e então continue o fluxo normalmente. Se a '
            "transcrição ficou confusa/sem sentido, peça gentilmente pra ele "
            "repetir — por escrito ou em outro áudio."
        )

    return base + "".join(extras)


# ---------------------------------------------------------------------------
# Gemini provider
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _configure_gemini() -> None:
    """Configura o SDK do Gemini com a API key (uma vez por processo)."""
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY não configurada no .env")
    genai.configure(api_key=settings.gemini_api_key)


def _build_gemini_history(history: list[dict]) -> list[dict]:
    """Converte histórico OpenAI-style para Gemini-style (sem a última msg)."""
    out: list[dict] = []
    for m in history[:-1]:
        role = m.get("role")
        content = m.get("content", "")
        if not content or role not in ("user", "assistant"):
            continue
        out.append(
            {
                "role": "user" if role == "user" else "model",
                "parts": [content],
            }
        )
    return out


def _ask_malu_gemini_sync(
    history: list[dict], system_prompt: str, json_mode: bool = False
) -> str:
    """Chamada síncrona ao Gemini — wrappeada em to_thread no async caller."""
    _configure_gemini()

    generation_config = (
        {"response_mime_type": "application/json"} if json_mode else None
    )
    model = genai.GenerativeModel(
        model_name=settings.gemini_model,
        system_instruction=system_prompt,
        generation_config=generation_config,
    )

    gemini_history = _build_gemini_history(history)
    chat = model.start_chat(history=gemini_history)

    last_message = history[-1].get("content", "")
    response = chat.send_message(last_message)
    _log_usage("gemini", settings.gemini_model, getattr(response, "usage_metadata", None), json_mode)
    return (getattr(response, "text", "") or "").strip()


async def _ask_malu_gemini(
    history: list[dict], system_prompt: str, json_mode: bool = False
) -> str:
    """Adapter async do Gemini — usa to_thread (SDK é majoritariamente sync)."""
    return await asyncio.to_thread(
        _ask_malu_gemini_sync, history, system_prompt, json_mode
    )


# ---------------------------------------------------------------------------
# Groq provider
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _groq_client() -> AsyncGroq:
    """Client Groq compartilhado (criado uma vez por processo)."""
    if not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY não configurada no .env")
    return AsyncGroq(api_key=settings.groq_api_key)


def _build_openai_messages(
    history: list[dict],
    system_prompt: str,
) -> list[dict]:
    """Formato OpenAI/Groq: system + alternância user/assistant."""
    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    for m in history:
        role = m.get("role")
        content = m.get("content", "")
        if not content or role not in ("user", "assistant"):
            continue
        messages.append({"role": role, "content": content})
    return messages


async def _ask_malu_groq(
    history: list[dict],
    system_prompt: str,
    json_mode: bool = False,
    model: str | None = None,
) -> str:
    """Chama o Groq (cliente async nativo). `model` permite usar o modelo de
    reserva do Groq sem mexer no principal."""
    client = _groq_client()
    messages = _build_openai_messages(history, system_prompt)

    kwargs: dict[str, Any] = {
        "model": model or settings.groq_model,
        "messages": messages,
        "max_tokens": _MAX_TOKENS,
        # 0.2 (não 0.7): respostas mais previsíveis e aderentes às regras —
        # menos escapes (preço/milhas/inglês). Extração JSON segue em 0.0.
        "temperature": 0.0 if json_mode else 0.2,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    response = await client.chat.completions.create(**kwargs)  # type: ignore[arg-type]
    _log_usage("groq", kwargs["model"], getattr(response, "usage", None), json_mode)

    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""
    message = choices[0].message
    return (getattr(message, "content", "") or "").strip()


# ---------------------------------------------------------------------------
# Providers OpenAI-compatible (Cerebras = perna grátis, Mistral = piso pago)
# ---------------------------------------------------------------------------
async def _ask_openai_compat(
    provider: str,
    base_url: str,
    api_key: str,
    model: str,
    history: list[dict],
    system_prompt: str,
    json_mode: bool = False,
) -> tuple[str, int]:
    """Chama um endpoint OpenAI-compatible (Cerebras/Mistral) via httpx.

    Reusa o `httpx` que já é dependência — não precisa de SDK novo. Retorna
    `(texto, total_tokens)`; o total alimenta a trava de orçamento do piso pago.
    """
    if not api_key:
        raise RuntimeError(f"{provider.upper()}_API_KEY não configurada")

    messages = _build_openai_messages(history, system_prompt)
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": _MAX_TOKENS,
        # Mesma régua do Groq: 0.2 no chat (aderente às regras), 0.0 na extração.
        "temperature": 0.0 if json_mode else 0.2,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    usage = data.get("usage") or {}
    total = int(usage.get("total_tokens") or 0)
    kind = "extract" if json_mode else "chat"
    logger.info(
        "[ai.usage] %s/%s kind=%s prompt=%s completion=%s total=%s",
        provider, model, kind,
        usage.get("prompt_tokens"), usage.get("completion_tokens"), total,
    )

    choices = data.get("choices") or []
    if not choices:
        return "", total
    content = (choices[0].get("message") or {}).get("content") or ""
    return content.strip(), total


async def _ask_malu_cerebras(
    history: list[dict],
    system_prompt: str,
    json_mode: bool = False,
    model: str | None = None,
) -> str:
    """Perna GRÁTIS extra (Cerebras). Não treina com dados → seguro p/ PII."""
    text, _ = await _ask_openai_compat(
        "cerebras",
        settings.cerebras_base_url,
        settings.cerebras_api_key,
        model or settings.cerebras_model,
        history,
        system_prompt,
        json_mode,
    )
    return text


async def _ask_malu_mistral(
    history: list[dict],
    system_prompt: str,
    json_mode: bool = False,
    model: str | None = None,
) -> str:
    """PISO PAGO (Mistral). Contabiliza os tokens gastos pra trava de orçamento."""
    text, total = await _ask_openai_compat(
        "mistral",
        settings.mistral_base_url,
        settings.mistral_api_key,
        model or settings.paid_floor_model,
        history,
        system_prompt,
        json_mode,
    )
    await budget.record_paid_tokens(total)
    return text


# ---------------------------------------------------------------------------
# Dispatcher público
# ---------------------------------------------------------------------------
def _model_name(provider: str) -> str:
    """Nome do modelo de um provider específico."""
    if provider == "gemini":
        return settings.gemini_model
    if provider == "groq":
        return settings.groq_model
    if provider == "cerebras":
        return settings.cerebras_model
    if provider == "mistral":
        return settings.paid_floor_model
    return provider


def active_model_name() -> str:
    """Nome do modelo atualmente ativo (para logs e telemetria)."""
    return _model_name(settings.ai_primary)


def _provider_available(provider: str) -> bool:
    """True se o provider tem credencial configurada."""
    if provider == "gemini":
        return bool(settings.gemini_api_key)
    if provider == "groq":
        return bool(settings.groq_api_key)
    if provider == "cerebras":
        return bool(settings.cerebras_api_key)
    if provider == "mistral":
        return bool(settings.mistral_api_key)
    return False


def _groq_models() -> list[str]:
    """Modelo principal do Groq + reserva (modelo menor/rápido), sem repetir."""
    models = [settings.groq_model]
    fb = settings.groq_fallback_model
    if fb and fb != settings.groq_model:
        models.append(fb)
    return models


def _build_attempts() -> list[tuple[str, str]]:
    """Ordem de tentativas (provider, modelo) que `route_and_ask` percorre.

    Cadeia em produção (AI_PRIMARY=groq / AI_FALLBACK=gemini):
        groq/70b → groq/8b → cerebras (grátis) → mistral (PISO PAGO) → gemini.
    Cada perna só entra se tiver credencial (chave faltando = perna pulada,
    nunca quebra a fila). O piso pago entra só com PAID_FLOOR_ENABLED=true.

    Racional LGPD da ordem: o briefing carrega PII (nome, datas, às vezes
    passaporte/saúde). Groq, Cerebras e Mistral NÃO treinam com os dados —
    então a PII passa por eles ANTES do Gemini grátis (que treina), que fica
    como último recurso. Custo desprezível: o buffer grátis Groq+Cerebras
    (~1,6M tokens/dia) cobre o dia a dia, então o piso pago quase nunca é tocado.
    """
    attempts: list[tuple[str, str]] = []

    def add_provider(provider: str) -> None:
        if provider == "groq":
            for m in _groq_models():
                if ("groq", m) not in attempts:
                    attempts.append(("groq", m))
        else:
            pair = (provider, _model_name(provider))
            if pair not in attempts:
                attempts.append(pair)

    primary = settings.ai_primary
    add_provider(primary)

    # Perna GRÁTIS extra: Cerebras entra depois do primário e antes do pago.
    if _provider_available("cerebras"):
        add_provider("cerebras")

    # PISO PAGO: Mistral só com a flag ligada E chave presente.
    if settings.paid_floor_enabled and _provider_available("mistral"):
        add_provider("mistral")

    fallback = _resolve_fallback(primary)
    if fallback:
        add_provider(fallback)
    return attempts


def _attempt_label(provider: str, model: str) -> str:
    """Rótulo gravado em `Conversation.model_used` quando um attempt responde.

    Groq/Gemini mantêm o nome cru do modelo (compatível com o classificador e
    a telemetria já existentes). Cerebras/Mistral ganham prefixo `provider/` —
    senão o modelo Llama do Cerebras seria contado como Groq e o do Mistral
    cairia em "desconhecido" no painel.
    """
    if provider in ("groq", "gemini"):
        return model
    return f"{provider}/{model}"


def _resolve_fallback(primary: str) -> str | None:
    """Decide qual provider de reserva usar quando o primário falha.

    AI_FALLBACK:
        none   → sem fallback
        auto   → usa o "outro" provider (gemini<->groq), se tiver chave
        gemini → força fallback no Gemini
        groq   → força fallback no Groq
    """
    fb = settings.ai_fallback
    if fb == "none":
        return None
    if fb == "auto":
        other = "groq" if primary == "gemini" else "gemini"
        return other if _provider_available(other) else None
    if fb != primary and _provider_available(fb):
        return fb
    return None


async def _ask_provider(
    provider: str,
    history: list[dict],
    system_prompt: str,
    json_mode: bool = False,
    model: str | None = None,
) -> str:
    """Chama um provider específico pelo nome. `model` (opcional) sobrescreve
    o modelo padrão do provider — usado pela reserva de modelo do Groq."""
    if provider == "gemini":
        return await _ask_malu_gemini(history, system_prompt, json_mode)
    if provider == "groq":
        return await _ask_malu_groq(history, system_prompt, json_mode, model=model)
    if provider == "cerebras":
        return await _ask_malu_cerebras(history, system_prompt, json_mode, model=model)
    if provider == "mistral":
        return await _ask_malu_mistral(history, system_prompt, json_mode, model=model)
    raise ValueError(f"provider não suportado: {provider}")


async def ask_malu(
    history: list[dict],
    customer_context: dict[str, Any] | None = None,
) -> str:
    """Chama o provider de IA configurado em `AI_PRIMARY`.

    Args:
        history: lista de mensagens
            [{"role": "user"|"assistant", "content": "..."}]
            A última mensagem deve ser do usuário.
        customer_context: dict opcional com `name`/`is_first_turn` injetado
            no system prompt.

    Returns:
        Texto da resposta da Malu.

    Raises:
        ValueError: se `history` estiver vazio ou provider inválido.
        Exception: qualquer falha do SDK do provider — chamador decide fallback.
    """
    if not history:
        raise ValueError("history vazio")

    system_prompt = _build_system_prompt(customer_context)
    provider = settings.ai_primary
    return await _ask_provider(provider, history, system_prompt)


async def route_and_ask(
    history: list[dict],
    customer_context: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Router principal — percorre a cadeia de IA e para no 1º que responder.

    Ordem (vide `_build_attempts`): groq/70b → groq/8b → cerebras (grátis) →
    mistral (PISO PAGO) → gemini. Antes de chamar o Mistral, checa a trava de
    orçamento mensal: teto atingido → PULA o Mistral e segue. Só devolve
    "error" se TODAS as pernas falharem.

    Returns:
        (resposta, modelo_usado)
        modelo_usado ∈ {rótulo do modelo que respondeu (ex.: "mistral/<modelo>"),
        "error"}.
    """
    if not history:
        raise ValueError("history vazio")

    system_prompt = _build_system_prompt(customer_context)
    attempts = _build_attempts()

    for i, (provider, model) in enumerate(attempts):
        # PISO PAGO: antes de gastar no Mistral, respeita o teto mensal.
        if provider == "mistral" and await budget.paid_floor_cap_reached():
            logger.warning(
                "piso pago (mistral) PULADO: teto mensal de tokens atingido "
                "(cap=%s) — seguindo pra próxima perna",
                settings.monthly_paid_token_cap,
            )
            continue
        try:
            text = await _ask_provider(provider, history, system_prompt, model=model)
            if text:
                if i > 0:
                    logger.warning(
                        "fallback acionado: %s/%s assumiu após falha da 1ª opção",
                        provider,
                        model,
                    )
                return text, _attempt_label(provider, model)
            logger.warning("%s/%s retornou resposta vazia", provider, model)
        except Exception:
            logger.exception("%s/%s call failed", provider, model)
            # segue para a próxima tentativa (reserva), se houver

    return (
        "Tive um probleminha técnico aqui agora. Pode me mandar de novo daqui a pouco?",
        "error",
    )


# ---------------------------------------------------------------------------
# Extração ESTRUTURADA do briefing (JSON) — substitui o regex frágil
# ---------------------------------------------------------------------------
def _render_transcript(history: list[dict]) -> str:
    """Achata o histórico num texto 'Cliente: ... / Malu: ...' pra extração."""
    lines: list[str] = []
    for m in history:
        role = m.get("role")
        content = (m.get("content") or "").strip()
        if not content or role not in ("user", "assistant"):
            continue
        who = "Cliente" if role == "user" else "Malu"
        lines.append(f"{who}: {content}")
    return "\n".join(lines)


def _build_extraction_prompt() -> str:
    """Instrução focada de extração — lista os campos a partir do briefing."""
    from app.briefing import BRIEFING_FIELDS, TEMPERATURA_KEY

    campos = "\n".join(f'  - "{k}": {label}' for k, label in BRIEFING_FIELDS)
    return (
        "Você é um EXTRATOR de dados. A partir da conversa entre um cliente e a "
        "assistente Malu, devolva UM objeto JSON com exatamente as chaves abaixo.\n\n"
        "REGRAS INVIOLÁVEIS:\n"
        "1. Use SOMENTE o que o CLIENTE disse explicitamente. NUNCA invente, "
        "suponha ou deduza.\n"
        "2. Todo campo que o cliente não informou claramente deve ser null.\n"
        "3. Ignore qualquer resumo que a própria Malu tenha escrito — baseie-se "
        "apenas nas falas do cliente.\n"
        f'4. A chave "{TEMPERATURA_KEY}" é a ÚNICA que você classifica: '
        '"frio", "morno", "quente" ou "urgente", conforme o interesse/urgência '
        'demonstrado (default "morno").\n\n'
        "Chaves do JSON:\n"
        f"{campos}\n"
        f'  - "{TEMPERATURA_KEY}": frio | morno | quente | urgente\n\n'
        "Responda APENAS com o objeto JSON, sem texto fora dele."
    )


def _parse_json_object(raw: str) -> dict | None:
    """Parseia o JSON da extração, tolerando cercas ```json e texto ao redor."""
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text[:4].lower() == "json":
            text = text[4:]
    text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


async def extract_lead_data(history: list[dict]) -> dict | None:
    """Extrai o briefing em JSON estruturado a partir da conversa.

    Tenta o provider primário e, em falha, o de reserva (mesma lógica do chat).
    Retorna None se nenhum provider devolver JSON válido — o chamador decide
    o fallback (ex.: voltar pro parser regex).
    """
    if not history:
        return None

    instruction = _build_extraction_prompt()
    transcript = _render_transcript(history)
    synth = [{"role": "user", "content": f"Conversa:\n{transcript}\n\nExtraia o JSON."}]

    primary = settings.ai_primary
    providers = [primary]
    fallback = _resolve_fallback(primary)
    if fallback:
        providers.append(fallback)

    for provider in providers:
        try:
            raw = await _ask_provider(provider, synth, instruction, json_mode=True)
            data = _parse_json_object(raw)
            if data is not None:
                return data
            logger.warning("extração via %s devolveu JSON inválido", provider)
        except Exception:
            logger.exception("extract_lead_data via %s falhou", provider)

    return None

"""Router de IA multi-provider — Gemini (primário) ou Groq (stand-by).

A escolha do provider é feita em runtime via `settings.ai_primary`:
    AI_PRIMARY=gemini   → usa Google Gemini (AI Studio)
    AI_PRIMARY=groq     → usa Groq (Llama 3.3 70B)

Trocar de provider é só mudar a variável no `.env` e reiniciar a aplicação.
O system prompt da Malu (`app/prompts/malu_v4.md`) é o mesmo nos dois casos.
"""

from __future__ import annotations

import asyncio
import logging
from functools import lru_cache
from pathlib import Path

import google.generativeai as genai
from groq import AsyncGroq

from app.config import settings

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent / "prompts" / "malu_v4.md"

# Limite conservador — respostas longas demais ficam ruins no WhatsApp
_MAX_TOKENS = 1024


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _load_system_prompt() -> str:
    """Carrega o system prompt da Malu (cached em memória)."""
    if not PROMPT_PATH.exists():
        raise FileNotFoundError(
            f"system prompt da Malu não encontrado em {PROMPT_PATH}"
        )
    return PROMPT_PATH.read_text(encoding="utf-8")


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


def _ask_malu_gemini_sync(history: list[dict]) -> str:
    """Chamada síncrona ao Gemini — wrappeada em to_thread no async caller."""
    _configure_gemini()
    system_prompt = _load_system_prompt()

    model = genai.GenerativeModel(
        model_name=settings.gemini_model,
        system_instruction=system_prompt,
    )

    gemini_history = _build_gemini_history(history)
    chat = model.start_chat(history=gemini_history)

    last_message = history[-1].get("content", "")
    response = chat.send_message(last_message)
    return (getattr(response, "text", "") or "").strip()


async def _ask_malu_gemini(history: list[dict]) -> str:
    """Adapter async do Gemini — usa to_thread (SDK é majoritariamente sync)."""
    return await asyncio.to_thread(_ask_malu_gemini_sync, history)


# ---------------------------------------------------------------------------
# Groq provider
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _groq_client() -> AsyncGroq:
    """Client Groq compartilhado (criado uma vez por processo)."""
    if not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY não configurada no .env")
    return AsyncGroq(api_key=settings.groq_api_key)


def _build_openai_messages(history: list[dict]) -> list[dict]:
    """Formato OpenAI/Groq: system + alternância user/assistant."""
    messages: list[dict] = [
        {"role": "system", "content": _load_system_prompt()}
    ]
    for m in history:
        role = m.get("role")
        content = m.get("content", "")
        if not content or role not in ("user", "assistant"):
            continue
        messages.append({"role": role, "content": content})
    return messages


async def _ask_malu_groq(history: list[dict]) -> str:
    """Chama o Groq (cliente async nativo)."""
    client = _groq_client()
    messages = _build_openai_messages(history)

    response = await client.chat.completions.create(
        model=settings.groq_model,
        messages=messages,  # type: ignore[arg-type]
        max_tokens=_MAX_TOKENS,
        temperature=0.7,
    )

    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""
    message = choices[0].message
    return (getattr(message, "content", "") or "").strip()


# ---------------------------------------------------------------------------
# Dispatcher público
# ---------------------------------------------------------------------------
def _model_name(provider: str) -> str:
    """Nome do modelo de um provider específico."""
    if provider == "gemini":
        return settings.gemini_model
    if provider == "groq":
        return settings.groq_model
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
    return False


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


async def _ask_provider(provider: str, history: list[dict]) -> str:
    """Chama um provider específico pelo nome."""
    if provider == "gemini":
        return await _ask_malu_gemini(history)
    if provider == "groq":
        return await _ask_malu_groq(history)
    raise ValueError(f"provider não suportado: {provider}")


async def ask_malu(history: list[dict]) -> str:
    """Chama o provider de IA configurado em `AI_PRIMARY`.

    Args:
        history: lista de mensagens
            [{"role": "user"|"assistant", "content": "..."}]
            A última mensagem deve ser do usuário.

    Returns:
        Texto da resposta da Malu.

    Raises:
        ValueError: se `history` estiver vazio ou provider inválido.
        Exception: qualquer falha do SDK do provider — chamador decide fallback.
    """
    if not history:
        raise ValueError("history vazio")

    provider = settings.ai_primary
    if provider == "gemini":
        return await _ask_malu_gemini(history)
    if provider == "groq":
        return await _ask_malu_groq(history)
    raise ValueError(f"AI_PRIMARY não suportado neste build: {provider}")


async def route_and_ask(history: list[dict]) -> tuple[str, str]:
    """Router principal — tenta o provider ativo e, em falha, o de reserva.

    A ordem é: AI_PRIMARY primeiro; se ele falhar ou vier vazio (ex.: limite
    de quota 429 do Gemini), tenta automaticamente o provider de AI_FALLBACK.

    Returns:
        (resposta, modelo_usado)
        modelo_usado ∈ {nome do modelo que respondeu, "error"}.
    """
    if not history:
        raise ValueError("history vazio")

    primary = settings.ai_primary
    providers = [primary]
    fallback = _resolve_fallback(primary)
    if fallback:
        providers.append(fallback)

    for i, provider in enumerate(providers):
        try:
            text = await _ask_provider(provider, history)
            if text:
                if i > 0:
                    logger.warning(
                        "fallback acionado: %s assumiu após falha do primário (%s)",
                        provider,
                        primary,
                    )
                return text, _model_name(provider)
            logger.warning("%s retornou resposta vazia", provider)
        except Exception:
            logger.exception("%s call failed", provider)
            # segue para o próximo provider (fallback), se houver

    return (
        "Tive um probleminha técnico aqui agora. Pode me mandar de novo daqui a pouco?",
        "error",
    )

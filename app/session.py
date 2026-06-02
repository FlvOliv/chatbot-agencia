"""Histórico de conversa por número — armazenado em Redis com TTL.

Cada entrada é uma lista de mensagens no formato OpenAI/Anthropic:
    [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
"""

from __future__ import annotations

import json
import logging
from typing import Any

import redis.asyncio as redis_asyncio

from app.config import settings

logger = logging.getLogger(__name__)

_redis_client: redis_asyncio.Redis | None = None


def _key(phone: str) -> str:
    return f"malu:session:{phone}"


def get_redis() -> redis_asyncio.Redis:
    """Retorna client Redis async (singleton)."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis_asyncio.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


def set_redis_client(client: redis_asyncio.Redis) -> None:
    """Injeta client (útil em testes — ex.: fakeredis)."""
    global _redis_client
    _redis_client = client


async def close_redis() -> None:
    """Fecha conexão Redis (chamar no shutdown)."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


async def get_history(phone: str) -> list[dict[str, Any]]:
    """Busca histórico de mensagens do número.

    Retorna lista vazia se a sessão não existir.
    """
    client = get_redis()
    try:
        raw = await client.get(_key(phone))
    except Exception:
        logger.exception("redis get_history failed for %s", phone)
        return []
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if not isinstance(data, list):
            return []
        return data
    except json.JSONDecodeError:
        logger.warning("invalid JSON in session %s — resetting", phone)
        return []


async def save_history(phone: str, history: list[dict[str, Any]]) -> None:
    """Persiste histórico com TTL configurado (default 24h)."""
    client = get_redis()
    payload = json.dumps(history, ensure_ascii=False)
    try:
        await client.set(_key(phone), payload, ex=settings.session_ttl_seconds)
    except Exception:
        logger.exception("redis save_history failed for %s", phone)


async def clear_history(phone: str) -> None:
    """Remove a sessão de um número."""
    client = get_redis()
    try:
        await client.delete(_key(phone))
    except Exception:
        logger.exception("redis clear_history failed for %s", phone)


# ---------------------------------------------------------------------------
# Estado de fluxo da sessão — máquina de estados leve
# ---------------------------------------------------------------------------
# Estados possíveis:
#   None                 → fluxo normal (default)
#   "awaiting_intent"    → cliente com reserva ativa precisa escolher
#                          1) atendimento sobre reserva  2) nova viagem
#   "transferred"        → Lu assumiu a conversa, Malu fica em silêncio
STATE_AWAITING_INTENT = "awaiting_intent"
STATE_TRANSFERRED = "transferred"

# TTL do estado igual ao da sessão — eles caem juntos quando o cliente some
def _state_key(phone: str) -> str:
    return f"malu:state:{phone}"


async def get_state(phone: str) -> str | None:
    """Lê o estado de fluxo atual da sessão (None = fluxo normal)."""
    client = get_redis()
    try:
        return await client.get(_state_key(phone))
    except Exception:
        logger.exception("redis get_state failed for %s", phone)
        return None


async def set_state(phone: str, state: str) -> None:
    """Persiste o estado de fluxo (TTL igual ao da sessão)."""
    client = get_redis()
    try:
        await client.set(_state_key(phone), state, ex=settings.session_ttl_seconds)
    except Exception:
        logger.exception("redis set_state failed for %s", phone)


async def clear_state(phone: str) -> None:
    """Remove o estado de fluxo (volta ao default)."""
    client = get_redis()
    try:
        await client.delete(_state_key(phone))
    except Exception:
        logger.exception("redis clear_state failed for %s", phone)

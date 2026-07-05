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

    Retorna lista vazia se a sessão não existir (nil = conversa nova ou expirada).
    Mas se o REDIS FALHAR (blip/conexão/cota estourada), NÃO devolve vazio calado
    — reconstrói o histórico recente do Postgres (fallback anti-amnésia), senão a
    Malu trataria a conversa como nova e re-saudaria/re-perguntaria tudo.
    """
    client = get_redis()
    try:
        raw = await client.get(_key(phone))
    except Exception:
        logger.exception(
            "redis get_history falhou p/ %s — reconstruindo do Postgres", phone
        )
        return await _history_from_db(phone)
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


# Fallback anti-amnésia: quando o Redis FALHA, reconstrói o histórico recente do
# Postgres (a conversa já é persistida em `conversations`). Só as últimas N
# mensagens DENTRO da janela da sessão — não ressuscita conversa antiga (>TTL),
# o que preservaria o "começo do zero" depois de 24h de inatividade.
_DB_FALLBACK_LIMIT = 20


async def _history_from_db(phone: str) -> list[dict[str, Any]]:
    """Reconstrói o histórico recente do Postgres quando o Redis está fora.

    Últimas `_DB_FALLBACK_LIMIT` mensagens dentro de `session_ttl_seconds`, em
    ordem cronológica. Degrada pra [] se o banco também falhar (nunca levanta).
    """
    try:
        from datetime import datetime, timedelta, timezone

        from sqlalchemy import select

        from app.database import SessionLocal
        from app.models import Conversation

        cutoff = datetime.now(timezone.utc) - timedelta(
            seconds=settings.session_ttl_seconds
        )
        async with SessionLocal() as db:
            result = await db.execute(
                select(
                    Conversation.role, Conversation.content, Conversation.created_at
                )
                .where(
                    Conversation.phone == phone,
                    Conversation.created_at >= cutoff,
                )
                .order_by(Conversation.created_at.desc())
                .limit(_DB_FALLBACK_LIMIT)
            )
            rows = list(result.all())
    except Exception:
        logger.exception("fallback Postgres do histórico falhou p/ %s", phone)
        return []

    history: list[dict[str, Any]] = []
    for role, content, _created in reversed(rows):  # desc → cronológico
        if role not in ("user", "assistant"):
            continue
        text = (content or "").strip()
        if not text:
            continue
        text = text.removeprefix("🎤 ").strip()  # tira o marcador visual de áudio
        history.append({"role": role, "content": text})
    if history:
        logger.warning(
            "get_history: %d msgs reconstruídas do Postgres p/ %s (Redis fora)",
            len(history),
            phone,
        )
    return history


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


async def get_states(phones: list[str]) -> dict[str, str | None]:
    """Lê o estado de vários phones num round-trip (MGET — evita N+1)."""
    if not phones:
        return {}
    client = get_redis()
    try:
        values = await client.mget([_state_key(p) for p in phones])
    except Exception:
        logger.exception("redis get_states failed")
        return {}
    return dict(zip(phones, values))


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


# ---------------------------------------------------------------------------
# Ficha da coleta — última extração BOA persistida (resiliência da Alavanca B)
# ---------------------------------------------------------------------------
# A extração por turno morre sob pico/cota (visto ao vivo em 05/07: Groq 429 →
# cadeia fallback instável → ficha None → digest/nudge/gate voando às cegas).
# A ficha persistida degrada isso pra "estado de 1-2 turnos atrás", que ainda
# preserva o anti-repergunta e o gate por tipo. Mesmo TTL da sessão — caem
# juntas quando o cliente some.


def _coleta_key(phone: str) -> str:
    return f"malu:coleta:{phone}"


async def get_coleta_state(phone: str) -> dict[str, Any] | None:
    """Última ficha de coleta persistida (None se não houver ou o Redis falhar)."""
    client = get_redis()
    try:
        raw = await client.get(_coleta_key(phone))
    except Exception:
        logger.exception("redis get_coleta_state failed for %s", phone)
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("invalid JSON in coleta_state %s — ignorando", phone)
        return None
    return data if isinstance(data, dict) else None


async def save_coleta_state(phone: str, data: dict[str, Any]) -> None:
    """Persiste a ficha de coleta com o TTL da sessão."""
    client = get_redis()
    try:
        await client.set(
            _coleta_key(phone),
            json.dumps(data, ensure_ascii=False),
            ex=settings.session_ttl_seconds,
        )
    except Exception:
        logger.exception("redis save_coleta_state failed for %s", phone)


async def clear_coleta_state(phone: str) -> None:
    """Remove a ficha (fim da coleta ou /sair — não vaza pra próxima cotação)."""
    client = get_redis()
    try:
        await client.delete(_coleta_key(phone))
    except Exception:
        logger.exception("redis clear_coleta_state failed for %s", phone)

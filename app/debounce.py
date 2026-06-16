"""Debounce de mensagens em rajada (Fase 1C).

Quando o cliente manda várias mensagens picadas seguidas, chamar a IA uma vez
por mensagem estoura o limite do Groq (429) e deixa a Malu repetitiva. Em vez
disso, a gente ESPERA alguns segundos e JUNTA tudo numa só chamada.

Algoritmo (estado no Redis → sobrevive a reinício e a vários servidores):
    1. Cada mensagem entra num buffer (lista Redis) por telefone.
    2. Cada mensagem grava um "token" marcando-se como a mais recente.
    3. Cada mensagem espera ``DEBOUNCE_SECONDS``.
    4. Ao acordar, só a ÚLTIMA (cujo token ainda é o mais recente) segue: lê +
       limpa o buffer e devolve o texto juntado. As anteriores desistem — a
       última responde por todas.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from app.config import settings
from app.session import get_redis

logger = logging.getLogger(__name__)

_BUF_KEY = "debounce:buf:{}"
_LATEST_KEY = "debounce:latest:{}"
_TTL = 120  # segundos — o buffer some sozinho se algo der errado no meio


async def collect_burst(phone: str, text: str) -> list[str] | None:
    """Bufferiza ``text`` e espera a rajada do cliente terminar.

    Returns:
        - lista com TODAS as mensagens da rajada (na ordem), se este chamador
          for o último — ele deve responder por todas;
        - ``None``, se uma mensagem mais nova chegou durante a espera — este
          chamador desiste (o último responde por todos).
    """
    client = get_redis()
    buf_key = _BUF_KEY.format(phone)
    latest_key = _LATEST_KEY.format(phone)
    token = uuid.uuid4().hex

    try:
        await client.rpush(buf_key, text)
        await client.expire(buf_key, _TTL)
        await client.set(latest_key, token, ex=_TTL)
    except Exception:
        # Se o Redis falhar, não trava o cliente: responde só esta mensagem.
        logger.exception("debounce: falha ao bufferizar %s — segue sem juntar", phone)
        return [text]

    await asyncio.sleep(settings.debounce_seconds)

    try:
        current = await client.get(latest_key)
        if current != token:
            return None  # chegou mensagem mais nova — este chamador desiste

        parts = await client.lrange(buf_key, 0, -1)
        await client.delete(buf_key)
        await client.delete(latest_key)
    except Exception:
        logger.exception("debounce: falha ao ler buffer de %s — responde só a atual", phone)
        return [text]

    return parts or [text]

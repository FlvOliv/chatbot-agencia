"""Testes do debounce de rajada (Fase 1C) — usa fakeredis (conftest global)."""

from __future__ import annotations

import pytest

from app import debounce
from app.session import get_redis


@pytest.mark.asyncio
async def test_collect_burst_single_message_returns_it(monkeypatch) -> None:
    """Uma mensagem só → volta ela mesma, e o buffer fica limpo."""
    monkeypatch.setattr(debounce.settings, "debounce_seconds", 0)

    result = await debounce.collect_burst("5511999990000", "oi")

    assert result == ["oi"]
    # buffer e token limpos após o flush
    client = get_redis()
    assert await client.lrange(debounce._BUF_KEY.format("5511999990000"), 0, -1) == []
    assert await client.get(debounce._LATEST_KEY.format("5511999990000")) is None


@pytest.mark.asyncio
async def test_collect_burst_combines_buffered_messages(monkeypatch) -> None:
    """O último da rajada junta TODAS as mensagens que estavam no buffer."""
    monkeypatch.setattr(debounce.settings, "debounce_seconds", 0)
    phone = "5511999991111"

    # Simula uma mensagem anterior já bufferizada (rajada em andamento).
    client = get_redis()
    await client.rpush(debounce._BUF_KEY.format(phone), "primeira")

    result = await debounce.collect_burst(phone, "segunda")

    assert result == ["primeira", "segunda"]


@pytest.mark.asyncio
async def test_collect_burst_loser_returns_none(monkeypatch) -> None:
    """Se uma mensagem mais nova chega durante a espera, este chamador desiste."""
    phone = "5511999992222"

    async def fake_sleep(_seconds) -> None:  # noqa: ANN001
        # Durante a "espera", chega uma mensagem mais nova (outro token).
        client = get_redis()
        await client.set(debounce._LATEST_KEY.format(phone), "token-mais-novo")

    monkeypatch.setattr(debounce.asyncio, "sleep", fake_sleep)

    result = await debounce.collect_burst(phone, "oi")

    assert result is None

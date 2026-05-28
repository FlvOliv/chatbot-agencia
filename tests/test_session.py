"""Testes do módulo app.session (Redis com TTL)."""

from __future__ import annotations

import pytest

from app.config import settings
from app.session import clear_history, get_history, save_history


@pytest.mark.asyncio
async def test_get_history_empty_returns_empty_list() -> None:
    history = await get_history("5511000000001")
    assert history == []


@pytest.mark.asyncio
async def test_save_and_get_history_roundtrip() -> None:
    phone = "5511000000002"
    payload = [
        {"role": "user", "content": "Oi, quero viajar"},
        {"role": "assistant", "content": "Oi! Eu sou a Malu"},
    ]
    await save_history(phone, payload)

    got = await get_history(phone)
    assert got == payload


@pytest.mark.asyncio
async def test_clear_history_removes_session() -> None:
    phone = "5511000000003"
    await save_history(phone, [{"role": "user", "content": "x"}])
    await clear_history(phone)
    assert await get_history(phone) == []


@pytest.mark.asyncio
async def test_ttl_is_set(fake_redis) -> None:
    phone = "5511000000004"
    await save_history(phone, [{"role": "user", "content": "ttl"}])

    ttl = await fake_redis.ttl(f"malu:session:{phone}")
    # fakeredis retorna o TTL configurado (≈ session_ttl_seconds)
    assert 0 < ttl <= settings.session_ttl_seconds


@pytest.mark.asyncio
async def test_invalid_json_returns_empty(fake_redis) -> None:
    phone = "5511000000005"
    await fake_redis.set(f"malu:session:{phone}", "not-json{")
    assert await get_history(phone) == []

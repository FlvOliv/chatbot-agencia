"""Fixtures globais — env de teste + fakeredis."""

from __future__ import annotations

import os

# Variáveis dummy precisam estar setadas ANTES de importar app.config.
os.environ.setdefault("WA_TOKEN", "test_token")
os.environ.setdefault("WA_PHONE_ID", "1234567890")
os.environ.setdefault("WA_VERIFY_TOKEN", "test_verify")
os.environ.setdefault("WA_APP_SECRET", "test_secret")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("GEMINI_MODEL", "gemini-2.5-flash")
os.environ.setdefault("GROQ_API_KEY", "test-groq-key")
os.environ.setdefault("GROQ_MODEL", "llama-3.3-70b-versatile")
os.environ.setdefault("LUCIANA_PHONE", "5511999999999")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://malu:malu@localhost:5432/malu"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("AI_PRIMARY", "gemini")
os.environ.setdefault("CRM_API_KEY", "test-api-key-123")
os.environ.setdefault("CRM_CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("AI_FALLBACK", "none")
os.environ.setdefault("APP_ENV", "development")

import pytest
import pytest_asyncio
from fakeredis import aioredis as fakeredis_aio

from app import session as session_module


@pytest_asyncio.fixture(autouse=True)
async def _fake_redis():
    """Substitui o client Redis real por fakeredis em todos os testes."""
    client = fakeredis_aio.FakeRedis(decode_responses=True)
    session_module.set_redis_client(client)
    try:
        yield client
    finally:
        await client.flushall()
        await client.aclose()
        session_module._redis_client = None  # type: ignore[attr-defined]


@pytest.fixture
def fake_redis(_fake_redis):
    return _fake_redis

"""Testes da Alavanca A — fallback anti-amnésia do histórico (Redis → Postgres)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app import session


# ---------------------------------------------------------------------------
# get_history: quando usar o fallback e quando NÃO usar
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_history_normal_le_do_redis(fake_redis) -> None:
    await session.save_history("5511", [{"role": "user", "content": "oi"}])
    assert await session.get_history("5511") == [{"role": "user", "content": "oi"}]


@pytest.mark.asyncio
async def test_get_history_cai_pro_postgres_quando_redis_falha(
    fake_redis, monkeypatch
) -> None:
    """Redis levanta exceção (blip/cota) → reconstrói do Postgres (não re-saúda)."""

    async def boom(key):  # noqa: ANN001
        raise RuntimeError("redis down")

    reconstruido = [{"role": "user", "content": "quero ir pra Recife"}]

    async def fake_db(phone):  # noqa: ANN001
        return reconstruido

    monkeypatch.setattr(fake_redis, "get", boom)
    monkeypatch.setattr(session, "_history_from_db", fake_db)

    assert await session.get_history("5511") == reconstruido


@pytest.mark.asyncio
async def test_get_history_nil_nao_usa_fallback(fake_redis, monkeypatch) -> None:
    """Redis responde nil (conversa nova/expirada, SEM erro) → [] sem tocar o DB
    (preserva o 'começo do zero' após 24h e não custa query na conversa nova)."""
    called: dict[str, bool] = {}

    async def fake_db(phone):  # noqa: ANN001
        called["db"] = True
        return []

    monkeypatch.setattr(session, "_history_from_db", fake_db)

    assert await session.get_history("5511-novo") == []
    assert "db" not in called


# ---------------------------------------------------------------------------
# _history_from_db: mapeamento, filtro, ordem
# ---------------------------------------------------------------------------
class _FakeResult:
    def __init__(self, rows):  # noqa: ANN001
        self._rows = rows

    def all(self):  # noqa: ANN001
        return self._rows


class _FakeDBSession:
    def __init__(self, rows):  # noqa: ANN001
        self._rows = rows

    async def __aenter__(self):  # noqa: ANN001
        return self

    async def __aexit__(self, *a):  # noqa: ANN001
        return False

    async def execute(self, stmt):  # noqa: ANN001
        return _FakeResult(self._rows)


@pytest.mark.asyncio
async def test_history_from_db_mapeia_filtra_e_ordena(monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    # Ordem DESC (mais nova primeiro), como a query devolve:
    rows = [
        ("assistant", "resposta 2", now),
        ("user", "🎤 pergunta 2", now),  # marcador de áudio some
        ("assistant", "resposta 1", now),
        ("user", "pergunta 1", now),
        ("assistant", "", now),  # vazio → filtrado
        ("system", "ruído", now),  # role inválido → filtrado
    ]
    monkeypatch.setattr("app.database.SessionLocal", lambda: _FakeDBSession(rows))

    out = await session._history_from_db("5511")

    assert out == [
        {"role": "user", "content": "pergunta 1"},
        {"role": "assistant", "content": "resposta 1"},
        {"role": "user", "content": "pergunta 2"},
        {"role": "assistant", "content": "resposta 2"},
    ]


@pytest.mark.asyncio
async def test_history_from_db_vazio_quando_banco_falha(monkeypatch) -> None:
    def boom():  # noqa: ANN001
        raise RuntimeError("db down")

    monkeypatch.setattr("app.database.SessionLocal", boom)
    assert await session._history_from_db("5511") == []

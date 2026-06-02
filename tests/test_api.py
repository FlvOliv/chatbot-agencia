"""Testes das rotas /api/* (consumidas pelo CRM)."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

# Configura uma API key conhecida ANTES de importar o app
os.environ.setdefault("CRM_API_KEY", "test-api-key-123")

from app.database import get_session  # noqa: E402
from app.main import app  # noqa: E402

API_KEY = "test-api-key-123"


# ---------------------------------------------------------------------------
# DB mock — evita que os testes dependam de Postgres real
# ---------------------------------------------------------------------------
class _FakeResult:
    """Mock de SQLAlchemy Result — retorna tudo vazio/zero."""

    def scalar_one(self):  # noqa: ANN001
        return 0

    def scalar_one_or_none(self):  # noqa: ANN001
        return None

    def scalars(self):
        return self

    def all(self):
        return []


class _FakeSession:
    """Mock mínimo de AsyncSession pra testes de roteamento."""

    async def execute(self, *args, **kwargs):  # noqa: ANN001, ARG002
        return _FakeResult()

    async def commit(self):  # noqa: ANN001
        pass

    async def rollback(self):  # noqa: ANN001
        pass

    async def flush(self):  # noqa: ANN001
        pass


async def _fake_get_session():
    yield _FakeSession()


@pytest.fixture
def client() -> TestClient:
    """Client com get_session mockado — não toca em Postgres real."""
    app.dependency_overrides[get_session] = _fake_get_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"X-API-Key": API_KEY}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def test_api_without_key_returns_401(client: TestClient) -> None:
    r = client.get("/api/leads")
    assert r.status_code == 401


def test_api_with_wrong_key_returns_401(client: TestClient) -> None:
    r = client.get("/api/leads", headers={"X-API-Key": "errado"})
    assert r.status_code == 401


def test_api_with_correct_key_passes_auth(
    client: TestClient, auth_headers
) -> None:
    """Com key correta E DB mockado, rota responde 200 com lista vazia."""
    r = client.get("/api/leads", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["items"] == []
    assert data["total"] == 0


def test_api_dashboard_metrics_with_correct_key(
    client: TestClient, auth_headers
) -> None:
    """Endpoint de métricas também responde com DB mockado."""
    r = client.get("/api/dashboard/metrics", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    # Todos os contadores zerados (banco fake)
    assert data["leads_today"] == 0
    assert data["leads_week"] == 0
    assert data["by_temperature"] == {"frio": 0, "morno": 0, "quente": 0, "urgente": 0}


# ---------------------------------------------------------------------------
# Estrutura das rotas
# ---------------------------------------------------------------------------
def test_routes_are_registered(client: TestClient) -> None:
    """Confirma que as rotas estão expostas (via OpenAPI schema)."""
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    assert "/api/leads" in paths
    assert "/api/leads/{phone}" in paths
    assert "/api/conversations" in paths
    assert "/api/conversations/{phone}" in paths
    assert "/api/reservas" in paths
    assert "/api/dashboard/metrics" in paths


def test_cors_headers_present(client: TestClient) -> None:
    """Preflight OPTIONS deve retornar headers CORS pro frontend Next.js."""
    r = client.options(
        "/api/leads",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-API-Key",
        },
    )
    # O CORSMiddleware do FastAPI cuida do preflight automaticamente
    assert "access-control-allow-origin" in {k.lower() for k in r.headers.keys()}

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


def test_config_requires_key(client: TestClient) -> None:
    r = client.get("/api/config")
    assert r.status_code == 401


def test_config_returns_non_secret_fields(client: TestClient, auth_headers) -> None:
    """/api/config devolve a config operacional (fonte única do painel)."""
    r = client.get("/api/config", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    # Campos esperados presentes
    for key in (
        "luciana_phone",
        "ai_primary",
        "ai_fallback",
        "business_hours_start",
        "business_hours_end",
        "app_env",
        "version",
    ):
        assert key in data
    # Nunca pode vazar segredo
    assert "wa_token" not in data
    assert "groq_api_key" not in data
    assert "crm_api_key" not in data
    assert "database_url" not in data


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
    assert "/api/leads/by-numero/{numero}" in paths
    assert "/api/conversations" in paths
    assert "/api/conversations/{phone}" in paths
    assert "/api/reservas" in paths
    assert "/api/dashboard/metrics" in paths
    assert "/api/config" in paths


def test_list_conversations_accepts_tag_id(client: TestClient, auth_headers) -> None:
    """Aceita ?tag_id=<uuid> (filtro server-side) — 200 + lista (DB fake = vazia)."""
    import uuid

    r = client.get(f"/api/conversations?tag_id={uuid.uuid4()}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_list_conversations_rejects_bad_tag_id(
    client: TestClient, auth_headers
) -> None:
    """tag_id que não é UUID → 422 (validação do FastAPI)."""
    r = client.get("/api/conversations?tag_id=nao-e-uuid", headers=auth_headers)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_delete_conversation_clears_log_and_memory() -> None:
    """delete_conversation apaga o log (DB) e limpa memória + estado (Redis)."""
    from app.api.conversations import delete_conversation
    from app.session import (
        STATE_TRANSFERRED,
        get_history,
        get_states,
        save_history,
        set_state,
    )

    phone = "5511999990000"
    await save_history(phone, [{"role": "user", "content": "teste antigo"}])
    await set_state(phone, STATE_TRANSFERRED)

    flags = {"deleted": False, "committed": False}

    class _DB:
        async def execute(self, *a, **k):  # noqa: ANN001, ANN002, ANN003, ARG002
            flags["deleted"] = True

        async def commit(self):  # noqa: ANN001
            flags["committed"] = True

    resp = await delete_conversation(phone, _DB())

    assert resp.status_code == 204
    assert flags["deleted"] and flags["committed"]
    assert await get_history(phone) == []  # memória limpa
    assert (await get_states([phone])).get(phone) is None  # estado limpo


def test_create_lead_rejects_bad_temp(client: TestClient, auth_headers) -> None:
    """POST /api/leads com lead_temp inválido → 422 (antes de tocar o banco)."""
    r = client.post(
        "/api/leads",
        headers=auth_headers,
        json={"phone": "5511988887777", "lead_temp": "mornissimo"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_lead_sets_fields() -> None:
    """create_lead monta o Lead com os campos enviados (e aplica strip no phone)."""
    from app.api.leads import create_lead
    from app.api.schemas import LeadIn

    added: dict = {}

    class _DB:
        def add(self, obj):  # noqa: ANN001
            added["lead"] = obj

        async def commit(self):  # noqa: ANN001
            pass

        async def refresh(self, obj):  # noqa: ANN001, ARG002
            pass

    lead = await create_lead(
        LeadIn(phone=" 5511988887777 ", name="Maria", destination="Recife", lead_temp="quente"),
        _DB(),
    )
    assert lead is added["lead"]
    assert lead.phone == "5511988887777"
    assert lead.name == "Maria"
    assert lead.lead_temp == "quente"


@pytest.mark.asyncio
async def test_delete_lead_404_when_missing() -> None:
    """delete_lead → 404 quando o número não existe."""
    from fastapi import HTTPException

    from app.api.leads import delete_lead

    class _Res:
        rowcount = 0

    class _DB:
        async def execute(self, *a, **k):  # noqa: ANN001, ANN002, ANN003, ARG002
            return _Res()

        async def commit(self):  # noqa: ANN001
            pass

    with pytest.raises(HTTPException) as exc:
        await delete_lead(999999, _DB())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_lead_204_when_found() -> None:
    """delete_lead → 204 + commit quando o número existe."""
    from app.api.leads import delete_lead

    flags = {"committed": False}

    class _Res:
        rowcount = 1

    class _DB:
        async def execute(self, *a, **k):  # noqa: ANN001, ANN002, ANN003, ARG002
            return _Res()

        async def commit(self):  # noqa: ANN001
            flags["committed"] = True

    resp = await delete_lead(1001, _DB())
    assert resp.status_code == 204
    assert flags["committed"]


def test_conversation_detail_includes_audio_url(monkeypatch, auth_headers) -> None:
    """Mensagem de voz (media_path) → a rota devolve audio_url (link assinado)."""
    import uuid as _uuid
    from datetime import datetime, timezone

    from app.models import Conversation

    conv = Conversation(
        id=str(_uuid.uuid4()),
        phone="5511955554444",
        role="user",
        content="🎤 quero ir pra bariloche",
        model_used=None,
        media_path="5511955554444/a.ogg",
        created_at=datetime.now(timezone.utc),
    )

    class _Result:
        def scalars(self):
            return self

        def all(self):
            return [conv]

        def scalar_one_or_none(self):
            return None  # sem cliente cadastrado

    class _Session:
        async def execute(self, *a, **k):  # noqa: ANN002, ANN003, ARG002
            return _Result()

        async def commit(self):
            pass

    async def _session_override():
        yield _Session()

    async def fake_signed(path):  # noqa: ANN001
        return f"https://signed.example/{path}"

    monkeypatch.setattr("app.api.conversations.signed_url", fake_signed)
    app.dependency_overrides[get_session] = _session_override
    try:
        c = TestClient(app)
        r = c.get("/api/conversations/5511955554444", headers=auth_headers)
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200
    msg = r.json()["messages"][0]
    assert msg["audio_url"] == "https://signed.example/5511955554444/a.ogg"


def test_get_lead_by_numero_returns_specific_quotation(monkeypatch, auth_headers) -> None:
    """A rota /api/leads/by-numero/{numero} abre uma cotação específica."""
    import uuid as _uuid
    from datetime import datetime, timezone

    from app.models import Lead

    now = datetime.now(timezone.utc)
    lead = Lead(
        id=str(_uuid.uuid4()),
        numero=1042,
        phone="5511955554444",
        name="Ana",
        destination="Rio de Janeiro",
        travel_type=None,
        lead_temp="quente",
        briefing_md="cotação X",
        raw_data={},
        created_at=now,
        updated_at=now,
    )

    class _Result:
        def __init__(self, one_or_none=None, one=0):
            self._oon = one_or_none
            self._one = one

        def scalar_one_or_none(self):
            return self._oon

        def scalar_one(self):
            return self._one

    class _Session:
        def __init__(self):
            self.calls = 0

        async def execute(self, *a, **k):  # noqa: ANN002, ANN003, ARG002
            self.calls += 1
            if self.calls == 1:
                return _Result(one_or_none=lead)  # busca do lead pelo numero
            if self.calls == 2:
                return _Result(one_or_none=None)  # cliente
            return _Result(one=3)  # contagem de mensagens

        async def commit(self):
            pass

    async def _session_override():
        yield _Session()

    app.dependency_overrides[get_session] = _session_override
    try:
        c = TestClient(app)
        r = c.get("/api/leads/by-numero/1042", headers=auth_headers)
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200
    body = r.json()
    assert body["lead"]["numero"] == 1042
    assert body["lead"]["phone"] == "5511955554444"
    assert body["conversation_count"] == 3


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

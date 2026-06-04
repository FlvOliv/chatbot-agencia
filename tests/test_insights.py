"""Testes do endpoint /api/dashboard/insights.

Mockamos os helpers async de agregação (`_conversations_per_day`, etc.) via
monkeypatch — isso desacopla os testes do SQL real e mantém o foco na
lógica de composição/preenchimento que vive dentro do handler.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("CRM_API_KEY", "test-api-key-123")

from app.api import metrics as metrics_module  # noqa: E402
from app.database import get_session  # noqa: E402
from app.main import app  # noqa: E402

API_KEY = "test-api-key-123"


# ---------------------------------------------------------------------------
# Fake session — só pra satisfazer a dependency. Os helpers que iriam tocar
# nele são substituídos por monkeypatch nos próprios testes.
# ---------------------------------------------------------------------------
class _FakeSession:
    async def execute(self, *args, **kwargs):  # noqa: ANN001, ARG002
        raise AssertionError(
            "Nenhum teste deveria chegar até execute() — "
            "todos os helpers foram mockados."
        )

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
    app.dependency_overrides[get_session] = _fake_get_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"X-API-Key": API_KEY}


# ---------------------------------------------------------------------------
# Helpers: instala stubs nos helpers de agregação do módulo metrics
# ---------------------------------------------------------------------------
def _patch_aggregators(
    monkeypatch: pytest.MonkeyPatch,
    *,
    convs_per_day: dict[date, int] | None = None,
    leads_per_day: dict[date, int] | None = None,
    top_destinations: list[tuple[str, int]] | None = None,
    hourly: dict[int, int] | None = None,
    conv_pair: tuple[int, int] = (0, 0),
    provider_rows: list[tuple[str | None, int]] | None = None,
) -> None:
    convs_per_day = convs_per_day or {}
    leads_per_day = leads_per_day or {}
    top_destinations = top_destinations or []
    hourly = hourly or {}
    provider_rows = provider_rows or []

    async def fake_convs(start):  # noqa: ARG001, ANN001
        return convs_per_day

    async def fake_leads(start):  # noqa: ARG001, ANN001
        return leads_per_day

    async def fake_top(start):  # noqa: ARG001, ANN001
        return top_destinations

    async def fake_hourly(start):  # noqa: ARG001, ANN001
        return hourly

    async def fake_conv(start):  # noqa: ARG001, ANN001
        return conv_pair

    async def fake_providers(start):  # noqa: ARG001, ANN001
        return provider_rows

    monkeypatch.setattr(metrics_module, "_conversations_per_day", fake_convs)
    monkeypatch.setattr(metrics_module, "_leads_per_day", fake_leads)
    monkeypatch.setattr(metrics_module, "_top_destinations_raw", fake_top)
    monkeypatch.setattr(metrics_module, "_hourly_distribution", fake_hourly)
    monkeypatch.setattr(metrics_module, "_conversion_inputs", fake_conv)
    monkeypatch.setattr(metrics_module, "_ai_provider_rows", fake_providers)


# ---------------------------------------------------------------------------
# 1. Auth
# ---------------------------------------------------------------------------
def test_insights_without_api_key_returns_401(
    client: TestClient, monkeypatch
) -> None:
    _patch_aggregators(monkeypatch)
    r = client.get("/api/dashboard/insights?days=7")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# 2. Estrutura básica com banco vazio
# ---------------------------------------------------------------------------
def test_insights_empty_db_returns_200_with_correct_structure(
    client: TestClient, auth_headers, monkeypatch
) -> None:
    _patch_aggregators(monkeypatch)
    r = client.get("/api/dashboard/insights?days=7", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()

    assert data["range_days"] == 7
    assert "generated_at" in data
    # 7 dias preenchidos
    assert len(data["conversations_per_day"]) == 7
    assert len(data["leads_per_day"]) == 7
    assert all(item["count"] == 0 for item in data["conversations_per_day"])
    assert all(item["count"] == 0 for item in data["leads_per_day"])

    assert data["top_destinations"] == []
    assert len(data["hourly_distribution"]) == 24
    assert data["conversion_rate"] == {
        "conversations_started": 0,
        "leads_generated": 0,
        "rate": 0.0,
    }
    assert data["ai_provider_breakdown"] == {
        "gemini": 0,
        "groq": 0,
        "unknown": 0,
    }


# ---------------------------------------------------------------------------
# 3. conversations_per_day preenche todos os dias do range
# ---------------------------------------------------------------------------
def test_conversations_per_day_fills_all_days_with_zero(
    client: TestClient, auth_headers, monkeypatch
) -> None:
    today = datetime.now(timezone.utc).date()
    # Só hoje tem dado; os outros 6 dias devem aparecer com count=0.
    _patch_aggregators(monkeypatch, convs_per_day={today: 5})

    r = client.get("/api/dashboard/insights?days=7", headers=auth_headers)
    assert r.status_code == 200
    series = r.json()["conversations_per_day"]

    assert len(series) == 7
    # Ordem cronológica (mais antigo → mais novo)
    parsed = [date.fromisoformat(item["date"]) for item in series]
    assert parsed == sorted(parsed)
    assert parsed[-1] == today
    # 6 zeros + 1 cinco
    counts = [item["count"] for item in series]
    assert counts.count(0) == 6
    assert counts[-1] == 5


# ---------------------------------------------------------------------------
# 4. top_destinations limita a 5 e calcula pct
# ---------------------------------------------------------------------------
def test_top_destinations_orders_and_limits(
    client: TestClient, auth_headers, monkeypatch
) -> None:
    # Já chega ordenado desc do "SQL" mockado, e limitado a 5.
    _patch_aggregators(
        monkeypatch,
        top_destinations=[
            ("Cancún", 8),
            ("Buenos Aires", 5),
            ("Orlando", 4),
            ("Lisboa", 2),
            ("Paris", 1),
        ],
    )

    r = client.get("/api/dashboard/insights?days=30", headers=auth_headers)
    assert r.status_code == 200
    top = r.json()["top_destinations"]

    assert len(top) == 5
    assert [t["destination"] for t in top] == [
        "Cancún",
        "Buenos Aires",
        "Orlando",
        "Lisboa",
        "Paris",
    ]
    # Ordenação desc confirmada
    counts = [t["count"] for t in top]
    assert counts == sorted(counts, reverse=True)
    # pct soma ~1 (fatia sobre o total dos top N)
    total = sum(counts)
    assert top[0]["pct"] == pytest.approx(8 / total)
    assert sum(t["pct"] for t in top) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 5. hourly_distribution sempre tem 24 entradas
# ---------------------------------------------------------------------------
def test_hourly_distribution_always_has_24_entries(
    client: TestClient, auth_headers, monkeypatch
) -> None:
    _patch_aggregators(monkeypatch, hourly={0: 2, 14: 9, 23: 5})

    r = client.get("/api/dashboard/insights?days=7", headers=auth_headers)
    assert r.status_code == 200
    buckets = r.json()["hourly_distribution"]

    assert len(buckets) == 24
    assert [b["hour"] for b in buckets] == list(range(24))
    by_hour = {b["hour"]: b["count"] for b in buckets}
    assert by_hour[0] == 2
    assert by_hour[14] == 9
    assert by_hour[23] == 5
    assert by_hour[1] == 0  # gap preenchido


# ---------------------------------------------------------------------------
# 6. conversion_rate — happy path e divide-by-zero
# ---------------------------------------------------------------------------
def test_conversion_rate_computes_and_handles_zero_denominator(
    client: TestClient, auth_headers, monkeypatch
) -> None:
    # Caso 1: 100 conversas, 25 leads → 0.25
    _patch_aggregators(monkeypatch, conv_pair=(100, 25))
    r = client.get("/api/dashboard/insights?days=7", headers=auth_headers)
    assert r.status_code == 200
    cr = r.json()["conversion_rate"]
    assert cr == {
        "conversations_started": 100,
        "leads_generated": 25,
        "rate": pytest.approx(0.25),
    }

    # Caso 2: 0 conversas, 0 leads → rate = 0.0 (sem ZeroDivisionError)
    _patch_aggregators(monkeypatch, conv_pair=(0, 0))
    r = client.get("/api/dashboard/insights?days=7", headers=auth_headers)
    assert r.status_code == 200
    cr = r.json()["conversion_rate"]
    assert cr["rate"] == 0.0
    assert cr["conversations_started"] == 0
    assert cr["leads_generated"] == 0


# ---------------------------------------------------------------------------
# 7. ai_provider_breakdown — mapeamento de prefixos
# ---------------------------------------------------------------------------
def test_ai_provider_breakdown_maps_model_prefixes(
    client: TestClient, auth_headers, monkeypatch
) -> None:
    _patch_aggregators(
        monkeypatch,
        provider_rows=[
            ("gemini-2.5-flash", 198),
            ("llama-3.3-70b-versatile", 12),
            ("groq-mixtral-8x7b", 3),
            (None, 4),
            ("anthropic-claude", 2),  # cai em "unknown"
        ],
    )

    r = client.get("/api/dashboard/insights?days=7", headers=auth_headers)
    assert r.status_code == 200
    ai = r.json()["ai_provider_breakdown"]

    assert ai["gemini"] == 198
    assert ai["groq"] == 12 + 3  # llama-* e groq-* somam
    assert ai["unknown"] == 4 + 2  # None + anthropic-*


# ---------------------------------------------------------------------------
# 8. Validação de days fora do range
# ---------------------------------------------------------------------------
def test_insights_rejects_days_out_of_range(
    client: TestClient, auth_headers, monkeypatch
) -> None:
    _patch_aggregators(monkeypatch)
    # days=0 e days=100 devem ser rejeitados (range 1..90)
    assert (
        client.get(
            "/api/dashboard/insights?days=0", headers=auth_headers
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/api/dashboard/insights?days=100", headers=auth_headers
        ).status_code
        == 422
    )


def test_insights_default_days_is_seven(
    client: TestClient, auth_headers, monkeypatch
) -> None:
    _patch_aggregators(monkeypatch)
    r = client.get("/api/dashboard/insights", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["range_days"] == 7

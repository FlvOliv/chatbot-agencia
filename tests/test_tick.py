"""Testes do endpoint do cron (/internal/tick) e da guarda do resumo diário."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app import reports
from app.config import settings
from app.main import app

CRON = "test-cron-secret"
TZ = ZoneInfo("America/Sao_Paulo")


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setattr(settings, "cron_secret", CRON)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Auth do endpoint
# ---------------------------------------------------------------------------
def test_tick_without_secret_401(client: TestClient) -> None:
    r = client.post("/internal/tick")
    assert r.status_code == 401


def test_tick_wrong_secret_401(client: TestClient) -> None:
    r = client.post("/internal/tick", headers={"X-Cron-Secret": "errado"})
    assert r.status_code == 401


def test_tick_blocked_when_secret_unset(monkeypatch) -> None:
    """Sem CRON_SECRET no servidor, o endpoint fica bloqueado (503), não aberto."""
    monkeypatch.setattr(settings, "cron_secret", "")
    c = TestClient(app)
    r = c.post("/internal/tick", headers={"X-Cron-Secret": "qualquer"})
    assert r.status_code == 503


def test_tick_ok_runs_both_jobs(client: TestClient) -> None:
    async def fake_due():  # noqa: ANN202
        return {"claimed": 1, "sent": 1}

    async def fake_report():  # noqa: ANN202
        return {"ran": False, "reason": "antes_da_hora"}

    with patch("app.api.tick.run_due_reminders", new=fake_due), patch(
        "app.api.tick.maybe_run_daily_report", new=fake_report
    ):
        r = client.post("/internal/tick", headers={"X-Cron-Secret": CRON})

    assert r.status_code == 200
    data = r.json()
    assert data["reminders"] == {"claimed": 1, "sent": 1}
    assert data["daily_report"]["reason"] == "antes_da_hora"


# ---------------------------------------------------------------------------
# maybe_run_daily_report — guarda 1×/dia (usa fakeredis do conftest)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_daily_report_outside_hour_does_not_run() -> None:
    # nem antes (7h) nem depois (10h) da hora do resumo (8h) → não toca no Redis
    for h in (7, 10):
        now = datetime(2026, 6, 23, h, 0, tzinfo=TZ)
        result = await reports.maybe_run_daily_report(now_local=now)
        assert result == {"ran": False, "reason": "fora_da_hora"}


@pytest.mark.asyncio
async def test_daily_report_runs_once_per_day() -> None:
    now = datetime(2026, 6, 23, 8, 0, tzinfo=TZ)  # dentro da hora do resumo

    async def fake_run():  # noqa: ANN202
        return {"total": 3, "counts": {}, "sent": True}

    with patch.object(reports, "run_daily_report", new=fake_run):
        r1 = await reports.maybe_run_daily_report(now_local=now)
        r2 = await reports.maybe_run_daily_report(now_local=now)

    assert r1["ran"] is True
    assert r1["total"] == 3
    assert r2 == {"ran": False, "reason": "ja_rodou_hoje"}

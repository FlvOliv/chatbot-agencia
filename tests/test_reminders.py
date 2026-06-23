"""Testes do agendamento de callbacks (Postgres) e do disparo via cron.

A camada de banco é mockada (a máquina não roda Postgres local) — checamos
contratos: schedule grava 30 min + pré-24h e apaga pendentes antes (supersede);
cancel apaga pendentes; run_due dispara os vencidos respeitando as travas
(Lu assumiu / sessão expirou). A lógica de HORÁRIO do pré-24h vive em
test_callbacks.py (função pura).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from app import reminders
from app.callbacks import CALLBACK_30M, CALLBACK_PRE24H, render_callback
from app.models import Reminder
from app.reminders import (
    KIND_30M,
    KIND_PRE24H,
    REMINDER_30M,
    THIRTY_MIN_SECONDS,
    _build_due_rows,
    _dispatch_one,
    cancel_reminders,
    run_due_reminders,
    schedule_callbacks,
)
from app.session import STATE_TRANSFERRED, save_history, set_state


# ---------------------------------------------------------------------------
# Fake session — async context manager que grava add()/execute()
# ---------------------------------------------------------------------------
class _FakeResult:
    def __init__(self, rows):  # noqa: ANN001
        self._rows = rows

    def scalars(self):  # noqa: ANN201
        return self

    def all(self):  # noqa: ANN201
        return self._rows


class _FakeSession:
    def __init__(self, select_rows=None):  # noqa: ANN001
        self.added: list = []
        self.executed: list = []
        self._rows = select_rows or []
        self.committed = False

    async def __aenter__(self):  # noqa: ANN204
        return self

    async def __aexit__(self, *a):  # noqa: ANN002, ANN204
        return False

    async def execute(self, stmt):  # noqa: ANN001, ANN201
        self.executed.append(stmt)
        return _FakeResult(self._rows)

    def add(self, obj):  # noqa: ANN001
        self.added.append(obj)

    async def commit(self):  # noqa: ANN201
        self.committed = True


# ---------------------------------------------------------------------------
# _build_due_rows (PURO)
# ---------------------------------------------------------------------------
def test_build_due_rows_always_has_30min() -> None:
    """O de 30 min sai SEMPRE (due = now + 1800s), mesmo sem pré-24h válido."""
    tz = ZoneInfo("America/Sao_Paulo")
    now = datetime(2026, 6, 23, 14, 0, tzinfo=tz)
    with patch.object(reminders, "_compute_pre24h_target", return_value=None):
        rows = _build_due_rows(now, now, "Ana", tz)

    assert len(rows) == 1
    kind, due_at, message = rows[0]
    assert kind == KIND_30M
    assert due_at == now + timedelta(seconds=THIRTY_MIN_SECONDS)
    assert message == render_callback(CALLBACK_30M, "Ana")


def test_build_due_rows_includes_pre24h_when_valid() -> None:
    """Havendo horário válido, sai também o pré-24h com aquele due_at."""
    tz = ZoneInfo("America/Sao_Paulo")
    now = datetime(2026, 6, 23, 14, 0, tzinfo=tz)
    alvo = datetime(2026, 6, 24, 13, 0, tzinfo=tz)
    with patch.object(reminders, "_compute_pre24h_target", return_value=alvo):
        rows = _build_due_rows(now, now, None, tz)

    assert len(rows) == 2
    assert rows[1] == (KIND_PRE24H, alvo, render_callback(CALLBACK_PRE24H, None))


# ---------------------------------------------------------------------------
# schedule_callbacks / cancel_reminders (banco mockado)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_schedule_callbacks_deletes_then_inserts() -> None:
    """Apaga pendentes (supersede) e insere os lembretes; commita."""
    fake = _FakeSession()
    with patch.object(reminders, "SessionLocal", lambda: fake), patch.object(
        reminders, "_compute_pre24h_target", return_value=None
    ):
        await schedule_callbacks("5511999999999", name="Ana")

    assert len(fake.executed) == 1  # o DELETE de supersede
    assert len(fake.added) == 1  # só o de 30 min (pré-24h = None)
    inserted = fake.added[0]
    assert isinstance(inserted, Reminder)
    assert inserted.phone == "5511999999999"
    assert inserted.kind == KIND_30M
    assert inserted.message == render_callback(CALLBACK_30M, "Ana")
    assert fake.committed is True


@pytest.mark.asyncio
async def test_schedule_callbacks_inserts_both_when_pre24h_valid() -> None:
    fake = _FakeSession()
    alvo = datetime(2026, 6, 24, 13, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    with patch.object(reminders, "SessionLocal", lambda: fake), patch.object(
        reminders, "_compute_pre24h_target", return_value=alvo
    ):
        await schedule_callbacks("5511888888888")

    kinds = sorted(r.kind for r in fake.added)
    assert kinds == [KIND_30M, KIND_PRE24H]


@pytest.mark.asyncio
async def test_cancel_reminders_deletes_and_commits() -> None:
    fake = _FakeSession()
    with patch.object(reminders, "SessionLocal", lambda: fake):
        await cancel_reminders("5511777777777")

    assert len(fake.executed) == 1  # o DELETE
    assert fake.added == []
    assert fake.committed is True


# ---------------------------------------------------------------------------
# _dispatch_one — travas (usa fakeredis do conftest)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_dispatch_sends_when_session_alive() -> None:
    phone = "5511222222222"
    await save_history(phone, [{"role": "user", "content": "oi"}])

    sent: list[tuple[str, str]] = []

    async def fake_send(to, text):  # noqa: ANN001
        sent.append((to, text))
        return True

    with patch.object(reminders, "send_message", side_effect=fake_send):
        ok = await _dispatch_one(phone, REMINDER_30M)

    assert ok is True
    assert sent == [(phone, REMINDER_30M)]


@pytest.mark.asyncio
async def test_dispatch_skips_when_transferred() -> None:
    phone = "5511444444444"
    await save_history(phone, [{"role": "user", "content": "oi"}])
    await set_state(phone, STATE_TRANSFERRED)

    sent: list = []

    async def fake_send(to, text):  # noqa: ANN001
        sent.append((to, text))
        return True

    with patch.object(reminders, "send_message", side_effect=fake_send):
        ok = await _dispatch_one(phone, REMINDER_30M)

    assert ok is False
    assert sent == []


@pytest.mark.asyncio
async def test_dispatch_skips_when_history_empty() -> None:
    phone = "5511333333333"  # sem save_history → sessão "expirada"

    sent: list = []

    async def fake_send(to, text):  # noqa: ANN001
        sent.append((to, text))
        return True

    with patch.object(reminders, "send_message", side_effect=fake_send):
        ok = await _dispatch_one(phone, REMINDER_30M)

    assert ok is False
    assert sent == []


# ---------------------------------------------------------------------------
# run_due_reminders — reivindica (marca sent_at) e dispara
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_run_due_claims_and_dispatches() -> None:
    p1, p2 = "5511230000001", "5511230000002"
    await save_history(p1, [{"role": "user", "content": "oi"}])
    await save_history(p2, [{"role": "user", "content": "oi"}])

    rows = [
        SimpleNamespace(phone=p1, message="m1", sent_at=None),
        SimpleNamespace(phone=p2, message="m2", sent_at=None),
    ]
    fake = _FakeSession(select_rows=rows)

    sent: list = []

    async def fake_send(to, text):  # noqa: ANN001
        sent.append((to, text))
        return True

    now = datetime(2026, 6, 23, 18, 0, tzinfo=timezone.utc)
    with patch.object(reminders, "SessionLocal", lambda: fake), patch.object(
        reminders, "send_message", side_effect=fake_send
    ):
        result = await run_due_reminders(now=now)

    assert result == {"claimed": 2, "sent": 2}
    assert sent == [(p1, "m1"), (p2, "m2")]
    # marcou sent_at ANTES de mandar (anti-duplicado) e commitou
    assert all(r.sent_at == now for r in rows)
    assert fake.committed is True


@pytest.mark.asyncio
async def test_run_due_skips_transferred_but_still_claims() -> None:
    """Vencido de quem a Lu assumiu é reivindicado (marcado) mas NÃO enviado."""
    phone = "5511230000003"
    await save_history(phone, [{"role": "user", "content": "oi"}])
    await set_state(phone, STATE_TRANSFERRED)

    rows = [SimpleNamespace(phone=phone, message="m", sent_at=None)]
    fake = _FakeSession(select_rows=rows)

    sent: list = []

    async def fake_send(to, text):  # noqa: ANN001
        sent.append((to, text))
        return True

    with patch.object(reminders, "SessionLocal", lambda: fake), patch.object(
        reminders, "send_message", side_effect=fake_send
    ):
        result = await run_due_reminders()

    assert result == {"claimed": 1, "sent": 0}
    assert sent == []
    assert rows[0].sent_at is not None  # reivindicado → não volta a disparar


# ---------------------------------------------------------------------------
# Constantes — sanity
# ---------------------------------------------------------------------------
def test_thirty_min_seconds() -> None:
    assert THIRTY_MIN_SECONDS == 1800


def test_reminder_30m_template_non_empty() -> None:
    assert REMINDER_30M and len(REMINDER_30M) > 20

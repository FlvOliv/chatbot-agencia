"""Testes do agendamento de callbacks (follow-ups) e da task send_reminder.

Mockamos o Celery — não disparamos jobs reais, só checamos contratos:
    - schedule_callbacks agenda SEMPRE o de 30 min (countdown 1800)
    - schedule_callbacks agenda o pré-24h quando há horário válido (via eta)
    - schedule_callbacks cancela o pendente antes (idempotência)
    - cancel_reminders revoga cada task_id e apaga a key no Redis
    - send_reminder pula transferido / sem histórico / superado (anti-spam)

A lógica de HORÁRIO do pré-24h é testada em test_callbacks.py (função pura).
"""

from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from app import reminders
from app.callbacks import CALLBACK_30M, CALLBACK_PRE24H, render_callback
from app.reminders import (
    REMINDER_30M,
    THIRTY_MIN_SECONDS,
    cancel_reminders,
    schedule_callbacks,
)
from app.session import STATE_TRANSFERRED, get_redis, set_state
from workers import tasks as workers_tasks


# ---------------------------------------------------------------------------
# schedule_callbacks
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_schedule_callbacks_always_schedules_30min() -> None:
    """O de 30 min é agendado SEMPRE (countdown 1800), mesmo sem pré-24h."""
    chamadas: list[dict] = []

    def fake_apply_async(args, **kwargs):  # noqa: ANN001
        chamadas.append({"args": args, "kwargs": kwargs})
        return SimpleNamespace(id=f"task-{len(chamadas)}")

    with patch.object(
        workers_tasks.send_reminder, "apply_async", side_effect=fake_apply_async
    ), patch.object(reminders, "_compute_pre24h_target", return_value=None):
        await schedule_callbacks("5511999999999", name="Ana")

    assert len(chamadas) == 1
    assert chamadas[0]["kwargs"].get("countdown") == THIRTY_MIN_SECONDS == 1800
    assert chamadas[0]["args"] == ["5511999999999", render_callback(CALLBACK_30M, "Ana")]


@pytest.mark.asyncio
async def test_schedule_callbacks_schedules_pre24h_when_valid() -> None:
    """Havendo horário válido, agenda também o pré-24h (via eta) e salva os 2 ids."""
    chamadas: list[dict] = []
    alvo = datetime(2026, 6, 18, 19, 59, 59, tzinfo=ZoneInfo("America/Sao_Paulo"))

    def fake_apply_async(args, **kwargs):  # noqa: ANN001
        chamadas.append({"args": args, "kwargs": kwargs})
        return SimpleNamespace(id=f"task-{len(chamadas)}")

    with patch.object(
        workers_tasks.send_reminder, "apply_async", side_effect=fake_apply_async
    ), patch.object(reminders, "_compute_pre24h_target", return_value=alvo):
        await schedule_callbacks("5511888888888", name=None)

    assert len(chamadas) == 2
    # 1º: 30 min por countdown
    assert chamadas[0]["kwargs"].get("countdown") == 1800
    # 2º: pré-24h por eta absoluto
    assert chamadas[1]["kwargs"].get("eta") == alvo
    assert chamadas[1]["args"] == ["5511888888888", render_callback(CALLBACK_PRE24H, None)]

    raw = await get_redis().get("malu:reminders:5511888888888")
    assert raw is not None and len(json.loads(raw)) == 2


@pytest.mark.asyncio
async def test_schedule_callbacks_cancels_before_scheduling() -> None:
    """Idempotência: chamar 2x revoga o job da 1ª antes de reagendar."""
    revoke_calls: list[str] = []

    def fake_apply_async(args, **kwargs):  # noqa: ANN001, ARG001
        return SimpleNamespace(id="job-1")

    def fake_revoke(task_id):  # noqa: ANN001
        revoke_calls.append(task_id)

    with patch.object(
        workers_tasks.send_reminder, "apply_async", side_effect=fake_apply_async
    ), patch.object(reminders, "_compute_pre24h_target", return_value=None), patch.object(
        workers_tasks.celery_app.control, "revoke", side_effect=fake_revoke
    ):
        await schedule_callbacks("5511777777777")
        assert revoke_calls == []  # nada a revogar na 1ª
        await schedule_callbacks("5511777777777")

    assert revoke_calls == ["job-1"]


# ---------------------------------------------------------------------------
# cancel_reminders
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cancel_reminders_revokes_each_task_id_and_deletes_key() -> None:
    phone = "5511666666666"
    client = get_redis()
    await client.set(f"malu:reminders:{phone}", json.dumps(["a", "b", "c"]))

    revoke_calls: list[str] = []

    def fake_revoke(task_id):  # noqa: ANN001
        revoke_calls.append(task_id)

    with patch.object(
        workers_tasks.celery_app.control, "revoke", side_effect=fake_revoke
    ):
        await cancel_reminders(phone)

    assert revoke_calls == ["a", "b", "c"]
    assert await client.get(f"malu:reminders:{phone}") is None


@pytest.mark.asyncio
async def test_cancel_reminders_noop_when_nothing_scheduled() -> None:
    revoke_calls: list[str] = []

    def fake_revoke(task_id):  # noqa: ANN001
        revoke_calls.append(task_id)

    with patch.object(
        workers_tasks.celery_app.control, "revoke", side_effect=fake_revoke
    ):
        await cancel_reminders("5511555555555")

    assert revoke_calls == []


# ---------------------------------------------------------------------------
# send_reminder task — caminhos de skip (inalterados)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_send_reminder_skips_when_transferred() -> None:
    phone = "5511444444444"
    await set_state(phone, STATE_TRANSFERRED)
    await get_redis().set(f"malu:reminders:{phone}", json.dumps(["tid-1"]))

    send_calls: list[tuple[str, str]] = []

    async def fake_send(to, text):  # noqa: ANN001
        send_calls.append((to, text))
        return True

    with patch.object(workers_tasks, "send_message", side_effect=fake_send):
        result = await workers_tasks._send_reminder_async(phone, REMINDER_30M, "tid-1")

    assert send_calls == []
    assert result["skipped"] == "transferred"
    assert result["sent"] is False


@pytest.mark.asyncio
async def test_send_reminder_skips_when_history_empty() -> None:
    phone = "5511333333333"
    await get_redis().set(f"malu:reminders:{phone}", json.dumps(["tid-1"]))

    send_calls: list[tuple[str, str]] = []

    async def fake_send(to, text):  # noqa: ANN001
        send_calls.append((to, text))
        return True

    with patch.object(workers_tasks, "send_message", side_effect=fake_send):
        result = await workers_tasks._send_reminder_async(phone, REMINDER_30M, "tid-1")

    assert send_calls == []
    assert result["skipped"] == "no_history"
    assert result["sent"] is False


@pytest.mark.asyncio
async def test_send_reminder_sends_when_session_alive() -> None:
    phone = "5511222222222"
    from app.session import save_history

    await save_history(phone, [{"role": "user", "content": "oi"}])
    await get_redis().set(f"malu:reminders:{phone}", json.dumps(["tid-1"]))

    send_calls: list[tuple[str, str]] = []

    async def fake_send(to, text):  # noqa: ANN001
        send_calls.append((to, text))
        return True

    with patch.object(workers_tasks, "send_message", side_effect=fake_send):
        result = await workers_tasks._send_reminder_async(phone, REMINDER_30M, "tid-1")

    assert send_calls == [(phone, REMINDER_30M)]
    assert result["sent"] is True


@pytest.mark.asyncio
async def test_send_reminder_skips_when_superseded() -> None:
    """ANTI-SPAM: lembrete cujo task_id não é o atual é ignorado."""
    phone = "5511220000000"
    from app.session import save_history

    await save_history(phone, [{"role": "user", "content": "oi"}])
    await get_redis().set(f"malu:reminders:{phone}", json.dumps(["id-novo"]))

    send_calls: list[tuple[str, str]] = []

    async def fake_send(to, text):  # noqa: ANN001
        send_calls.append((to, text))
        return True

    with patch.object(workers_tasks, "send_message", side_effect=fake_send):
        result = await workers_tasks._send_reminder_async(phone, REMINDER_30M, "id-velho")

    assert send_calls == []
    assert result["skipped"] == "superseded"
    assert result["sent"] is False


# ---------------------------------------------------------------------------
# Constantes — sanity
# ---------------------------------------------------------------------------
def test_thirty_min_seconds() -> None:
    assert THIRTY_MIN_SECONDS == 1800


def test_reminder_30m_template_non_empty() -> None:
    assert REMINDER_30M and len(REMINDER_30M) > 20

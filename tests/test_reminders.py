"""Testes dos lembretes de inatividade (Sprint 2).

Mockamos o Celery — não disparamos jobs reais, só checamos contratos:
    - schedule_reminders chama apply_async 3x com countdowns corretos
    - schedule_reminders chama cancel_reminders antes (idempotência)
    - cancel_reminders revoga cada task_id e apaga a key no Redis
    - send_reminder pula se state == TRANSFERRED
    - send_reminder pula se get_history retorna vazio
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app import reminders
from app.reminders import (
    REMINDER_15M,
    REMINDER_5H,
    REMINDER_23H,
    cancel_reminders,
    schedule_reminders,
)
from app.session import STATE_TRANSFERRED, get_redis, set_state
from workers import tasks as workers_tasks


# ---------------------------------------------------------------------------
# schedule_reminders
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_schedule_reminders_calls_apply_async_with_correct_countdowns() -> None:
    """Os 3 lembretes devem ser agendados com countdowns 900s, 18000s, 82800s."""
    chamadas: list[dict] = []

    def fake_apply_async(args, countdown):  # noqa: ANN001
        chamadas.append({"args": args, "countdown": countdown})
        # Mimic Celery AsyncResult
        return SimpleNamespace(id=f"task-{countdown}")

    with patch.object(
        workers_tasks.send_reminder, "apply_async", side_effect=fake_apply_async
    ):
        await schedule_reminders("5511999999999")

    assert len(chamadas) == 3
    assert [c["countdown"] for c in chamadas] == [900, 18000, 82800]
    assert chamadas[0]["args"] == ["5511999999999", REMINDER_15M]
    assert chamadas[1]["args"] == ["5511999999999", REMINDER_5H]
    assert chamadas[2]["args"] == ["5511999999999", REMINDER_23H]


@pytest.mark.asyncio
async def test_schedule_reminders_persists_task_ids_to_redis() -> None:
    """Os 3 task_ids retornados pelo Celery são salvos em malu:reminders:{phone}."""

    def fake_apply_async(args, countdown):  # noqa: ANN001, ARG001
        return SimpleNamespace(id=f"tid-{countdown}")

    with patch.object(
        workers_tasks.send_reminder, "apply_async", side_effect=fake_apply_async
    ):
        await schedule_reminders("5511888888888")

    client = get_redis()
    raw = await client.get("malu:reminders:5511888888888")
    assert raw is not None
    stored = json.loads(raw)
    assert stored == ["tid-900", "tid-18000", "tid-82800"]


@pytest.mark.asyncio
async def test_schedule_reminders_cancels_before_scheduling() -> None:
    """Idempotência: chamar schedule_reminders 2x não duplica jobs — a 2ª revoga a 1ª."""
    revoke_calls: list[str] = []

    def fake_apply_async(args, countdown):  # noqa: ANN001, ARG001
        return SimpleNamespace(id=f"new-{countdown}")

    def fake_revoke(task_id):  # noqa: ANN001
        revoke_calls.append(task_id)

    with patch.object(
        workers_tasks.send_reminder, "apply_async", side_effect=fake_apply_async
    ), patch.object(workers_tasks.celery_app.control, "revoke", side_effect=fake_revoke):
        # Primeira chamada — não há nada pra revogar
        await schedule_reminders("5511777777777")
        assert revoke_calls == []
        # Segunda chamada — deve revogar os 3 da primeira antes de reagendar
        await schedule_reminders("5511777777777")

    assert revoke_calls == ["new-900", "new-18000", "new-82800"]


# ---------------------------------------------------------------------------
# cancel_reminders
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cancel_reminders_revokes_each_task_id_and_deletes_key() -> None:
    """cancel_reminders chama revoke pra cada id e apaga a key Redis."""
    phone = "5511666666666"
    client = get_redis()
    await client.set(
        f"malu:reminders:{phone}", json.dumps(["a", "b", "c"])
    )

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
    """Sem key no Redis, cancel_reminders não chama revoke e não levanta."""
    revoke_calls: list[str] = []

    def fake_revoke(task_id):  # noqa: ANN001
        revoke_calls.append(task_id)

    with patch.object(
        workers_tasks.celery_app.control, "revoke", side_effect=fake_revoke
    ):
        await cancel_reminders("5511555555555")

    assert revoke_calls == []


# ---------------------------------------------------------------------------
# send_reminder task — caminhos de skip
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_send_reminder_skips_when_transferred() -> None:
    """Se state == TRANSFERRED, send_message NÃO é chamado."""
    phone = "5511444444444"
    await set_state(phone, STATE_TRANSFERRED)

    send_calls: list[tuple[str, str]] = []

    async def fake_send(to, text):  # noqa: ANN001
        send_calls.append((to, text))
        return True

    with patch.object(workers_tasks, "send_message", side_effect=fake_send):
        result = await workers_tasks._send_reminder_async(phone, REMINDER_15M)

    assert send_calls == []
    assert result["skipped"] == "transferred"
    assert result["sent"] is False


@pytest.mark.asyncio
async def test_send_reminder_skips_when_history_empty() -> None:
    """Se get_history retorna vazio (sessão expirou), send_message NÃO é chamado."""
    phone = "5511333333333"
    # Sem state e sem history — fakeredis está vazio para este número

    send_calls: list[tuple[str, str]] = []

    async def fake_send(to, text):  # noqa: ANN001
        send_calls.append((to, text))
        return True

    with patch.object(workers_tasks, "send_message", side_effect=fake_send):
        result = await workers_tasks._send_reminder_async(phone, REMINDER_5H)

    assert send_calls == []
    assert result["skipped"] == "no_history"
    assert result["sent"] is False


@pytest.mark.asyncio
async def test_send_reminder_sends_when_session_alive() -> None:
    """Caminho feliz: history não-vazio + state != TRANSFERRED → manda."""
    phone = "5511222222222"
    # Popula history mas não seta state
    from app.session import save_history

    await save_history(phone, [{"role": "user", "content": "oi"}])

    send_calls: list[tuple[str, str]] = []

    async def fake_send(to, text):  # noqa: ANN001
        send_calls.append((to, text))
        return True

    with patch.object(workers_tasks, "send_message", side_effect=fake_send):
        result = await workers_tasks._send_reminder_async(phone, REMINDER_23H)

    assert send_calls == [(phone, REMINDER_23H)]
    assert result["sent"] is True


# ---------------------------------------------------------------------------
# Constantes — sanity
# ---------------------------------------------------------------------------
def test_reminder_messages_are_distinct_and_non_empty() -> None:
    msgs = {REMINDER_15M, REMINDER_5H, REMINDER_23H}
    assert len(msgs) == 3
    for m in msgs:
        assert m and len(m) > 30


def test_reminder_schedule_countdowns() -> None:
    countdowns = [c for c, _ in reminders.REMINDER_SCHEDULE]
    assert countdowns == [900, 18000, 82800]

"""Lembrete de inatividade — agenda 1 follow-up assíncrono via Celery.

Sempre que a Malu responde e a coleta ainda está em aberto, agenda UM
lembrete para 30 min depois. Qualquer mensagem nova do cliente cancela o
lembrete pendente e reagenda — `schedule_reminders` é idempotente; quando o
briefing é finalizado, o chamador cancela e não reagenda.

O `task_id` do job Celery é guardado em Redis na key
`malu:reminders:{phone}` para podermos chamar `.revoke()` nele depois.
"""

from __future__ import annotations

import json
import logging

from app.session import get_redis

logger = logging.getLogger(__name__)

REMINDER_30M = (
    "Oi! Quando puder, é só continuar de onde paramos por aqui — "
    "faltam só alguns detalhes pra Lu preparar sua cotação. 😊"
)

# Lembrete ÚNICO: 30 min após a última mensagem da Malu. (countdown_segundos, mensagem)
REMINDER_SCHEDULE: tuple[tuple[int, str], ...] = (
    (30 * 60, REMINDER_30M),         # 1800s
)


def _key(phone: str) -> str:
    return f"malu:reminders:{phone}"


async def cancel_reminders(phone: str) -> None:
    """Revoga lembretes pendentes e apaga a key de tracking.

    Idempotente: se não houver nada agendado, é no-op.
    """
    client = get_redis()
    try:
        raw = await client.get(_key(phone))
    except Exception:
        logger.exception("redis get reminders failed for %s", phone)
        return

    if raw:
        try:
            task_ids = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("invalid JSON in reminders %s — resetting", phone)
            task_ids = []

        if isinstance(task_ids, list) and task_ids:
            # Import local para evitar ciclo (workers.tasks importa app.*)
            from workers.tasks import celery_app

            for tid in task_ids:
                try:
                    celery_app.control.revoke(tid)
                except Exception:
                    logger.exception("revoke reminder %s failed for %s", tid, phone)

    try:
        await client.delete(_key(phone))
    except Exception:
        logger.exception("redis delete reminders failed for %s", phone)


async def schedule_reminders(phone: str) -> None:
    """Agenda o lembrete único (30 min) para o número.

    Cancela qualquer lembrete pendente antes — chamadas repetidas não
    duplicam jobs.
    """
    await cancel_reminders(phone)

    # Import local para evitar ciclo (workers.tasks importa app.*)
    from workers.tasks import send_reminder

    task_ids: list[str] = []
    for countdown, message in REMINDER_SCHEDULE:
        try:
            result = send_reminder.apply_async(
                args=[phone, message],
                countdown=countdown,
            )
            task_ids.append(result.id)
        except Exception:
            logger.exception(
                "apply_async reminder failed for %s (countdown=%s)", phone, countdown
            )

    if not task_ids:
        return

    client = get_redis()
    try:
        await client.set(_key(phone), json.dumps(task_ids))
    except Exception:
        logger.exception("redis set reminders failed for %s", phone)

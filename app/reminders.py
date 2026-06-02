"""Lembretes de inatividade — agenda 3 follow-ups assíncronos via Celery.

Sempre que o cliente responde, a Malu agenda 3 lembretes a partir do
timestamp atual (15min / 5h / 23h). Qualquer mensagem nova cancela os
lembretes pendentes e reagenda — `schedule_reminders` é idempotente.

Os `task_ids` dos jobs Celery são guardados em Redis na key
`malu:reminders:{phone}` para podermos chamar `.revoke()` neles depois.
"""

from __future__ import annotations

import json
import logging

from app.session import get_redis

logger = logging.getLogger(__name__)

REMINDER_15M = (
    "Oi, ainda está por aí? Se preferir continuar depois, é só me chamar. "
    "Se quiser encerrar agora, digite `sair`."
)
REMINDER_5H = (
    "Estou guardando os dados da sua viagem aqui. "
    "Quando puder, é só responder e a gente continua de onde parou. 😊"
)
REMINDER_23H = (
    "Última chance pra hoje! Se não responder, vou arquivar essa conversa, "
    "mas pode me chamar de novo quando quiser."
)

# (countdown_segundos, mensagem)
REMINDER_SCHEDULE: tuple[tuple[int, str], ...] = (
    (15 * 60, REMINDER_15M),         # 900s
    (5 * 60 * 60, REMINDER_5H),      # 18000s
    (23 * 60 * 60, REMINDER_23H),    # 82800s
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
    """Agenda os 3 lembretes para o número.

    Cancela quaisquer lembretes pendentes antes — chamadas repetidas
    não duplicam jobs.
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

"""Celery tasks — follow-up de leads e relatório diário para Lu.

Para subir o worker em dev:
    celery -A workers.tasks worker --loglevel=info --beat

(`--beat` ativa o scheduler para o `daily_lead_report`.)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from celery import Celery
from celery.schedules import crontab
from sqlalchemy import func, select

from app.briefing import _format_phone_display  # type: ignore[attr-defined]
from app.config import settings
from app.database import SessionLocal
from app.models import Lead
from app.session import STATE_TRANSFERRED, get_history, get_state
from app.whatsapp import send_message

logger = logging.getLogger(__name__)

celery_app = Celery(
    "malu",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Sao_Paulo",
    enable_utc=True,
    task_acks_late=True,
    worker_max_tasks_per_child=200,
)

FOLLOWUP_TEXT = (
    "Oi! Só passando para ver se ainda posso te ajudar com a cotação da sua viagem. "
    "Se precisar, é só me chamar por aqui."
)


def _run(coro: Any) -> Any:
    """Roda uma corrotina dentro de uma task Celery (cada task → loop novo)."""
    return asyncio.run(coro)


@celery_app.task(name="malu.send_followup", bind=True, max_retries=3)
def send_followup(self, phone: str) -> dict[str, Any]:  # noqa: ARG001
    """Envia mensagem leve de follow-up para um cliente parado."""
    try:
        ok = _run(send_message(phone, FOLLOWUP_TEXT))
        return {"phone": phone, "sent": ok}
    except Exception as exc:
        logger.exception("send_followup failed for %s", phone)
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(name="malu.send_reminder", bind=True, max_retries=2)
def send_reminder(self, phone: str, message: str) -> dict[str, Any]:  # noqa: ARG001
    """Envia lembrete de inatividade — só se a sessão ainda estiver viva.

    Skips:
        - state == STATE_TRANSFERRED  (Lu já assumiu a conversa)
        - get_history vazio           (sessão Redis expirou — cliente sumiu)
    """
    try:
        return _run(_send_reminder_async(phone, message))
    except Exception as exc:
        logger.exception("send_reminder failed for %s", phone)
        raise self.retry(exc=exc, countdown=60)


async def _send_reminder_async(phone: str, message: str) -> dict[str, Any]:
    state = await get_state(phone)
    if state == STATE_TRANSFERRED:
        logger.info("reminder skipped for %s — transferred to Lu", phone)
        return {"phone": phone, "sent": False, "skipped": "transferred"}

    history = await get_history(phone)
    if not history:
        logger.info("reminder skipped for %s — session expired", phone)
        return {"phone": phone, "sent": False, "skipped": "no_history"}

    ok = await send_message(phone, message)
    return {"phone": phone, "sent": ok}


@celery_app.task(name="malu.daily_lead_report")
def daily_lead_report() -> dict[str, Any]:
    """Resumo dos leads do dia anterior agrupados por temperatura."""
    return _run(_daily_lead_report_async())


async def _daily_lead_report_async() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)

    async with SessionLocal() as db:
        stmt = (
            select(Lead.lead_temp, func.count(Lead.id))
            .where(Lead.created_at >= start, Lead.created_at < end)
            .group_by(Lead.lead_temp)
        )
        result = await db.execute(stmt)
        counts: dict[str, int] = {row[0] or "indefinido": int(row[1]) for row in result.all()}

    total = sum(counts.values())
    if total == 0:
        body = (
            f"📊 *Resumo Malu — {start.date().isoformat()}*\n\n"
            "Nenhum lead novo no dia anterior."
        )
    else:
        lines = "\n".join(
            f"• {temp.capitalize()}: {n}" for temp, n in sorted(counts.items())
        )
        body = (
            f"📊 *Resumo Malu — {start.date().isoformat()}*\n\n"
            f"Total: {total}\n{lines}"
        )

    sent = await send_message(settings.luciana_phone, body)
    logger.info("daily_lead_report total=%s sent=%s", total, sent)
    return {"total": total, "counts": counts, "sent": sent}


# Beat schedule — rodar todo dia às 8h America/Sao_Paulo
celery_app.conf.beat_schedule = {
    "daily-lead-report-8am": {
        "task": "malu.daily_lead_report",
        "schedule": crontab(hour=8, minute=0),
    },
}


__all__ = [
    "celery_app",
    "send_followup",
    "send_reminder",
    "daily_lead_report",
    "_format_phone_display",
]

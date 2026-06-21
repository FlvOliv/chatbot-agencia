"""Celery tasks — follow-up de leads e relatório diário para Lu.

Para subir o worker em dev:
    celery -A workers.tasks worker --loglevel=info --beat

(`--beat` ativa o scheduler para o `daily_lead_report`.)
"""

from __future__ import annotations

import asyncio
import json
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
from app.reminders import _key as _reminders_key
from app.session import STATE_TRANSFERRED, get_history, get_redis, get_state
from app.whatsapp import send_message

logger = logging.getLogger(__name__)

def _broker_url(url: str) -> str:
    """Celery/kombu exige `ssl_cert_reqs` explícito em URLs rediss:// (TLS).

    Sem isso, `apply_async` quebra com ValueError. Upstash tem certificado
    válido, então CERT_REQUIRED é seguro.
    """
    if url.startswith("rediss://") and "ssl_cert_reqs" not in url:
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}ssl_cert_reqs=CERT_REQUIRED"
    return url


_BROKER_URL = _broker_url(settings.redis_url)

# O broker Redis reentrega tarefas não confirmadas após `visibility_timeout`
# (default do kombu = 1h). O callback pré-24h fica ~23h agendado (ETA longo);
# com o default, o Redis acha que ele "se perdeu" e o reentrega de hora em hora,
# acumulando cópias que disparam JUNTAS quando o ETA chega → mensagens
# duplicadas. 25h cobre o ETA máximo (24h) com folga e mata a reentrega.
REMINDER_VISIBILITY_TIMEOUT = 25 * 60 * 60  # 90000s

celery_app = Celery(
    "malu",
    broker=_BROKER_URL,
    backend=_BROKER_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Sao_Paulo",
    enable_utc=True,
    task_acks_late=True,
    worker_max_tasks_per_child=200,
    broker_transport_options={"visibility_timeout": REMINDER_VISIBILITY_TIMEOUT},
    result_backend_transport_options={"visibility_timeout": REMINDER_VISIBILITY_TIMEOUT},
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
def send_reminder(self, phone: str, message: str) -> dict[str, Any]:
    """Envia lembrete de inatividade — só se ainda for o lembrete ATUAL e a
    sessão estiver viva.

    Skips (anti-spam — NUNCA disparar lembrete velho/empilhado):
        - task_id não está mais em `malu:reminders:{phone}` (foi cancelado ou
          substituído por uma mensagem mais nova — o revoke do Celery não é
          confiável, então conferimos aqui na hora de enviar)
        - state == STATE_TRANSFERRED  (Lu já assumiu a conversa)
        - get_history vazio           (sessão Redis expirou — cliente sumiu)
    """
    try:
        return _run(_send_reminder_async(phone, message, self.request.id))
    except Exception as exc:
        logger.exception("send_reminder failed for %s", phone)
        raise self.retry(exc=exc, countdown=60)


# TTL da marca "callback já enviado" (anti-duplicado). Precisa cobrir toda a
# janela em que cópias reentregues do MESMO job poderiam chegar (~24h + folga).
REMINDER_SENT_TTL = 26 * 60 * 60  # 93600s


def _sent_key(task_id: str) -> str:
    return f"malu:reminders:sent:{task_id}"


async def _release_claim(claim_key: str, phone: str) -> None:
    """Libera a marca anti-duplicado para um retry legítimo após falha de envio."""
    try:
        await get_redis().delete(claim_key)
    except Exception:
        logger.exception("reminder dedup: redis delete falhou para %s", phone)


async def _is_current_reminder(phone: str, task_id: str | None) -> bool:
    """True só se `task_id` ainda consta na lista de lembretes ATUAIS do número.

    Essa é a trava anti-spam: lembretes antigos (de antes de uma nova mensagem,
    ou já cancelados) não estão mais na chave → são ignorados no envio, mesmo
    que tenham ficado empilhados na fila do Celery.
    """
    if not task_id:
        return False
    try:
        raw = await get_redis().get(_reminders_key(phone))
    except Exception:
        logger.exception("reminder guard: redis get falhou para %s", phone)
        return False  # na dúvida, NÃO envia (seguro contra spam)
    if not raw:
        return False
    try:
        ids = json.loads(raw)
    except json.JSONDecodeError:
        return False
    return isinstance(ids, list) and task_id in ids


async def _send_reminder_async(
    phone: str, message: str, task_id: str | None = None
) -> dict[str, Any]:
    if not await _is_current_reminder(phone, task_id):
        logger.info("reminder skipped for %s — superseded/cancelled (%s)", phone, task_id)
        return {"phone": phone, "sent": False, "skipped": "superseded"}

    state = await get_state(phone)
    if state == STATE_TRANSFERRED:
        logger.info("reminder skipped for %s — transferred to Lu", phone)
        return {"phone": phone, "sent": False, "skipped": "transferred"}

    history = await get_history(phone)
    if not history:
        logger.info("reminder skipped for %s — session expired", phone)
        return {"phone": phone, "sent": False, "skipped": "no_history"}

    # Trava anti-duplicado: o broker pode reentregar o MESMO job (mesmo task_id)
    # — a checagem _is_current_reminder NÃO pega isso (id idêntico). Aqui só a
    # 1ª entrega "reivindica" o envio (SETNX atômico); cópias seguintes veem a
    # marca e pulam. Falha real de envio libera a marca para um retry legítimo.
    claim_key = _sent_key(task_id) if task_id else None
    if claim_key is not None:
        try:
            claimed = await get_redis().set(
                claim_key, "1", nx=True, ex=REMINDER_SENT_TTL
            )
        except Exception:
            logger.exception("reminder dedup: redis set falhou para %s", phone)
            return {"phone": phone, "sent": False, "skipped": "dedup_error"}
        if not claimed:
            logger.info("reminder skipped for %s — already sent (%s)", phone, task_id)
            return {"phone": phone, "sent": False, "skipped": "already_sent"}

    try:
        ok = await send_message(phone, message)
    except Exception:
        if claim_key is not None:
            await _release_claim(claim_key, phone)
        raise
    if not ok and claim_key is not None:
        await _release_claim(claim_key, phone)
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

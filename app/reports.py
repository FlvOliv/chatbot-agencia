"""Resumo diário de leads pra Lu — disparado pelo cron (antes era Celery beat).

A cada dia, um resumo dos leads do dia ANTERIOR agrupados por temperatura,
enviado pro WhatsApp da Lu. A decisão de QUANDO rodar (1×/dia, a partir das 8h)
fica no endpoint do cron (`app/api/tick.py`); aqui só o conteúdo + o envio.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.config import settings
from app.database import SessionLocal
from app.models import Lead
from app.session import get_redis
from app.whatsapp import send_message

logger = logging.getLogger(__name__)


def build_daily_report_body(report_date: str, counts: dict[str, int]) -> str:
    """Monta o texto do resumo (PURA — sem DB, sem rede). `counts` por temperatura."""
    total = sum(counts.values())
    header = f"📊 *Resumo Malu — {report_date}*\n\n"
    if total == 0:
        return header + "Nenhum lead novo no dia anterior."
    lines = "\n".join(
        f"• {temp.capitalize()}: {n}" for temp, n in sorted(counts.items())
    )
    return header + f"Total: {total}\n{lines}"


async def run_daily_report(now: datetime | None = None) -> dict[str, Any]:
    """Apura os leads do dia anterior e manda o resumo pra Lu."""
    now = now or datetime.now(timezone.utc)
    start = (now - timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    end = start + timedelta(days=1)

    async with SessionLocal() as db:
        stmt = (
            select(Lead.lead_temp, func.count(Lead.id))
            .where(Lead.created_at >= start, Lead.created_at < end)
            .group_by(Lead.lead_temp)
        )
        result = await db.execute(stmt)
        counts: dict[str, int] = {
            row[0] or "indefinido": int(row[1]) for row in result.all()
        }

    body = build_daily_report_body(start.date().isoformat(), counts)
    sent = await send_message(settings.luciana_phone, body)
    total = sum(counts.values())
    logger.info("daily_report total=%s sent=%s", total, sent)
    return {"total": total, "counts": counts, "sent": sent}


async def maybe_run_daily_report(now_local: datetime | None = None) -> dict[str, Any]:
    """Roda o resumo no máximo 1×/dia, a partir de `daily_report_hour`.

    Como o cron bate a cada minuto, só tentamos a trava DENTRO da hora do
    resumo (`daily_report_hour`) — fora dela, retorna na hora sem tocar no Redis
    (senão seriam ~960 comandos/dia). Dentro da hora, SETNX por data garante 1
    disparo só (a 1ª batida roda; as outras veem a marca e pulam). ~60 toques de
    Redis/dia no pior caso. Se o sistema ficar fora a hora inteira, pula o dia.
    """
    tz = ZoneInfo(settings.callback_timezone)
    now_local = now_local or datetime.now(tz)
    if now_local.hour != settings.daily_report_hour:
        return {"ran": False, "reason": "fora_da_hora"}

    key = f"malu:daily_report:{now_local.date().isoformat()}"
    try:
        claimed = await get_redis().set(key, "1", nx=True, ex=2 * 24 * 3600)
    except Exception:
        logger.exception("daily_report: trava no Redis falhou — pulando hoje")
        return {"ran": False, "reason": "redis_erro"}
    if not claimed:
        return {"ran": False, "reason": "ja_rodou_hoje"}

    result = await run_daily_report()
    return {"ran": True, **result}

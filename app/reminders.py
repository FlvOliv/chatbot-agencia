"""Follow-ups automáticos (callbacks) — agendados no Postgres, disparados por cron.

Substitui o antigo agendamento via Celery/Redis (que cutucava o Redis 24h sem
parar e estourava o limite do plano grátis do Upstash). Agora:

  • `schedule_callbacks` grava 1-2 linhas na tabela `reminders` (30 min + pré-24h).
  • `cancel_reminders` apaga os pendentes do número.
  • `run_due_reminders` (chamada por um cron a cada minuto via `/internal/tick`)
    dispara os vencidos — conferindo que a Lu não assumiu e a sessão está viva.

Dois callbacks, ambos só se a coleta seguir em aberto:

  • 30 min após a última mensagem da Malu — dispara SEMPRE (ignora o silêncio).
  • pré-24h — pouco antes de fechar a janela de 24h da Meta, respeitando o
    horário de silêncio (não acorda o cliente de madrugada) e um buffer.

Definições do pré-24h:
  t0 = última mensagem INBOUND do cliente (abre/renova a janela de 24h).
  C  = t0 + 24h  (prazo IMUTÁVEL da Meta — muda só o horário de disparo).
  alvo = C − buffer. Se o alvo cai no silêncio, puxa pro último instante
  antes do silêncio (ex.: 19:59:59). Nunca agenda ≥ C nem dentro do silêncio.

Supersede: cada mensagem nova do cliente chama `schedule_callbacks`, que APAGA
os pendentes antes de reinserir → nunca dispara um lembrete velho.
Anti-duplicado: `run_due_reminders` MARCA `sent_at` dentro de uma transação com
trava de linha (`FOR UPDATE SKIP LOCKED`) ANTES de mandar → batidas de cron
sobrepostas não disparam a mesma mensagem duas vezes.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select

from app.callbacks import CALLBACK_30M, CALLBACK_PRE24H, render_callback
from app.config import settings
from app.database import SessionLocal
from app.models import Reminder
from app.session import STATE_TRANSFERRED, get_history, get_state
from app.whatsapp import send_message

logger = logging.getLogger(__name__)

# 30 min após a última mensagem da Malu.
THIRTY_MIN_SECONDS = 30 * 60

# Rótulos do campo `kind` (espelham o CHECK da tabela `reminders`).
KIND_30M = "30m"
KIND_PRE24H = "pre24h"

# Quantos vencidos processar por batida do cron (folga enorme pro volume real).
_DISPATCH_BATCH = 50
# Lembretes já enviados são apagados depois disso (mantém a tabela enxuta).
_SENT_RETENTION_DAYS = 3

# Texto base do lembrete de 30 min (mantido pra compatibilidade de import; o
# texto canônico vive em app/callbacks.py e é renderizado com o nome).
REMINDER_30M = CALLBACK_30M


# ---------------------------------------------------------------------------
# Cálculo do horário do callback pré-24h (funções PURAS — testáveis sem DB)
# ---------------------------------------------------------------------------
def _in_quiet(dt: datetime, quiet_start: int, quiet_end: int) -> bool:
    """True se `dt` está no horário de silêncio [quiet_start, quiet_end)."""
    h = dt.hour
    if quiet_start < quiet_end:  # janela no mesmo dia (ex.: 1–6)
        return quiet_start <= h < quiet_end
    return h >= quiet_start or h < quiet_end  # janela que cruza a meia-noite (20–8)


def _last_instant_before_quiet(dt: datetime, quiet_start: int) -> datetime:
    """Último segundo antes do silêncio que contém/precede `dt` (ex.: 19:59:59).

    Pressupõe que `dt` está dentro do silêncio.
    """
    # O silêncio que contém dt começou às quiet_start:00 de algum dia:
    #   - tarde/noite (h >= quiet_start) → começou hoje
    #   - madrugada   (h <  quiet_start) → começou ontem
    day = dt.date() if dt.hour >= quiet_start else dt.date() - timedelta(days=1)
    quiet_begin = datetime(
        day.year, day.month, day.day, quiet_start, 0, 0, tzinfo=dt.tzinfo
    )
    return quiet_begin - timedelta(seconds=1)


def _compute_pre24h_target(
    t0: datetime,
    now: datetime,
    tz: ZoneInfo,
    quiet_start: int,
    quiet_end: int,
    buffer_minutes: int,
) -> datetime | None:
    """Horário de disparo do callback pré-24h, ou None se não houver válido.

    Regras: alvo = C − buffer; se no silêncio, puxa pro último instante antes
    do silêncio; nunca ≥ C nem dentro do silêncio; precisa ser futuro (> now).
    """
    t0 = t0.astimezone(tz)
    now = now.astimezone(tz)
    c = t0 + timedelta(hours=24)
    target = c - timedelta(minutes=buffer_minutes)

    if _in_quiet(target, quiet_start, quiet_end):
        candidate = _last_instant_before_quiet(target, quiet_start)
    else:
        candidate = target

    if now < candidate < c and not _in_quiet(candidate, quiet_start, quiet_end):
        return candidate
    return None


def _build_due_rows(
    t0: datetime, now: datetime, name: str | None, tz: ZoneInfo
) -> list[tuple[str, datetime, str]]:
    """Lembretes a agendar: lista de (kind, due_at, message). PURA (sem DB).

    Sempre inclui o de 30 min; inclui o pré-24h só se houver horário válido
    fora do silêncio.
    """
    rows: list[tuple[str, datetime, str]] = [
        (
            KIND_30M,
            now + timedelta(seconds=THIRTY_MIN_SECONDS),
            render_callback(CALLBACK_30M, name),
        )
    ]
    target = _compute_pre24h_target(
        t0,
        now,
        tz,
        settings.quiet_start,
        settings.quiet_end,
        settings.pre24h_buffer_minutes,
    )
    if target is not None:
        rows.append((KIND_PRE24H, target, render_callback(CALLBACK_PRE24H, name)))
    return rows


# ---------------------------------------------------------------------------
# Agendamento (Postgres)
# ---------------------------------------------------------------------------
async def schedule_callbacks(
    phone: str, t0: datetime | None = None, name: str | None = None
) -> None:
    """Agenda os callbacks (30 min + pré-24h) para o número.

    Apaga qualquer pendente antes — chamadas repetidas não duplicam (supersede).
    `t0` é a última mensagem do cliente (default: agora). `name` personaliza a
    saudação.
    """
    tz = ZoneInfo(settings.callback_timezone)
    now = datetime.now(tz)
    if t0 is None:
        t0 = now

    rows = _build_due_rows(t0, now, name, tz)

    try:
        async with SessionLocal() as db:
            await db.execute(
                delete(Reminder).where(
                    Reminder.phone == phone, Reminder.sent_at.is_(None)
                )
            )
            for kind, due_at, message in rows:
                db.add(
                    Reminder(phone=phone, kind=kind, message=message, due_at=due_at)
                )
            await db.commit()
    except Exception:
        logger.exception("schedule_callbacks falhou para %s", phone)


async def cancel_reminders(phone: str) -> None:
    """Apaga os callbacks pendentes do número. Idempotente."""
    try:
        async with SessionLocal() as db:
            await db.execute(
                delete(Reminder).where(
                    Reminder.phone == phone, Reminder.sent_at.is_(None)
                )
            )
            await db.commit()
    except Exception:
        logger.exception("cancel_reminders falhou para %s", phone)


# ---------------------------------------------------------------------------
# Disparo (chamado pelo cron via /internal/tick)
# ---------------------------------------------------------------------------
async def _dispatch_one(phone: str, message: str) -> bool:
    """Envia 1 lembrete se ainda fizer sentido. True se enviou.

    Pula se a Lu já assumiu (STATE_TRANSFERRED) ou a sessão Redis expirou
    (cliente sumiu) — mesmas travas do worker antigo.
    """
    if await get_state(phone) == STATE_TRANSFERRED:
        logger.info("lembrete pulado p/ %s — Lu assumiu", phone)
        return False
    if not await get_history(phone):
        logger.info("lembrete pulado p/ %s — sessão expirou", phone)
        return False
    return await send_message(phone, message)


async def run_due_reminders(now: datetime | None = None) -> dict[str, int]:
    """Dispara os lembretes vencidos. Chamada pelo cron a cada minuto.

    Reivindica os vencidos numa transação travada (FOR UPDATE SKIP LOCKED) +
    marca `sent_at` ANTES de mandar → batidas sobrepostas não duplicam. O envio
    (rede) acontece FORA da transação pra não segurar a conexão do banco.
    """
    now = now or datetime.now(timezone.utc)
    claimed: list[tuple[str, str]] = []

    try:
        async with SessionLocal() as db:
            result = await db.execute(
                select(Reminder)
                .where(Reminder.due_at <= now, Reminder.sent_at.is_(None))
                .order_by(Reminder.due_at)
                .with_for_update(skip_locked=True)
                .limit(_DISPATCH_BATCH)
            )
            rows = result.scalars().all()
            for r in rows:
                r.sent_at = now
                claimed.append((r.phone, r.message))
            # Higiene: apaga enviados antigos pra tabela não crescer pra sempre.
            await db.execute(
                delete(Reminder).where(
                    Reminder.sent_at
                    < now - timedelta(days=_SENT_RETENTION_DAYS)
                )
            )
            await db.commit()
    except Exception:
        logger.exception("run_due_reminders: falha ao reivindicar vencidos")
        return {"claimed": 0, "sent": 0}

    sent = 0
    for phone, message in claimed:
        try:
            if await _dispatch_one(phone, message):
                sent += 1
        except Exception:
            logger.exception("run_due_reminders: envio falhou para %s", phone)

    if claimed:
        logger.info("run_due_reminders: %s vencidos, %s enviados", len(claimed), sent)
    return {"claimed": len(claimed), "sent": sent}

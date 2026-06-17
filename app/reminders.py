"""Follow-ups automáticos (callbacks) — agenda via Celery.

Dois callbacks, ambos só se a coleta seguir em aberto:

  • 30 min após a última mensagem da Malu — dispara SEMPRE (ignora o silêncio).
  • pré-24h — pouco antes de fechar a janela de 24h da Meta, respeitando o
    horário de silêncio (não acorda o cliente de madrugada) e um buffer.

Definições do pré-24h:
  t0 = última mensagem INBOUND do cliente (abre/renova a janela de 24h).
  C  = t0 + 24h  (prazo IMUTÁVEL da Meta — muda só o horário de disparo).
  alvo = C − buffer. Se o alvo cai no silêncio, puxa pro último instante
  antes do silêncio (ex.: 19:59:59). Nunca agenda ≥ C nem dentro do silêncio;
  sem horário válido → não agenda.

Qualquer mensagem nova do cliente cancela os pendentes e reagenda a partir do
novo t0 — `schedule_callbacks` é idempotente. O `task_id` de cada job fica em
`malu:reminders:{phone}` (Redis) para `.revoke()` e para a trava anti-spam.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.callbacks import CALLBACK_30M, CALLBACK_PRE24H, render_callback
from app.config import settings
from app.session import get_redis

logger = logging.getLogger(__name__)

# 30 min após a última mensagem da Malu.
THIRTY_MIN_SECONDS = 30 * 60

# Texto base do lembrete de 30 min (mantido pra compatibilidade de import; o
# texto canônico vive em app/callbacks.py e é renderizado com o nome).
REMINDER_30M = CALLBACK_30M


def _key(phone: str) -> str:
    return f"malu:reminders:{phone}"


# ---------------------------------------------------------------------------
# Cálculo do horário do callback pré-24h (funções PURAS — testáveis sem Celery)
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


# ---------------------------------------------------------------------------
# Cancelamento
# ---------------------------------------------------------------------------
async def cancel_reminders(phone: str) -> None:
    """Revoga callbacks pendentes e apaga a key de tracking.

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


# ---------------------------------------------------------------------------
# Agendamento
# ---------------------------------------------------------------------------
async def schedule_callbacks(
    phone: str, t0: datetime | None = None, name: str | None = None
) -> None:
    """Agenda os callbacks (30 min + pré-24h) para o número.

    Cancela qualquer pendente antes — chamadas repetidas não duplicam jobs.
    `t0` é a última mensagem do cliente (default: agora). `name` personaliza
    a saudação.
    """
    await cancel_reminders(phone)

    tz = ZoneInfo(settings.callback_timezone)
    now = datetime.now(tz)
    if t0 is None:
        t0 = now

    # Import local para evitar ciclo (workers.tasks importa app.*)
    from workers.tasks import send_reminder

    task_ids: list[str] = []

    # 30 min — dispara sempre (ignora o silêncio).
    try:
        result = send_reminder.apply_async(
            args=[phone, render_callback(CALLBACK_30M, name)],
            countdown=THIRTY_MIN_SECONDS,
        )
        task_ids.append(result.id)
    except Exception:
        logger.exception("apply_async callback 30min falhou para %s", phone)

    # Pré-24h — respeita silêncio + buffer.
    target = _compute_pre24h_target(
        t0,
        now,
        tz,
        settings.quiet_start,
        settings.quiet_end,
        settings.pre24h_buffer_minutes,
    )
    if target is None:
        logger.info(
            "callback pré-24h não agendado para %s — sem horário válido fora do "
            "silêncio; reengajamento depende de template aprovado + opt-in",
            phone,
        )
    else:
        try:
            result = send_reminder.apply_async(
                args=[phone, render_callback(CALLBACK_PRE24H, name)],
                eta=target,
            )
            task_ids.append(result.id)
        except Exception:
            logger.exception("apply_async callback pré-24h falhou para %s", phone)

    if not task_ids:
        return

    client = get_redis()
    try:
        await client.set(_key(phone), json.dumps(task_ids))
    except Exception:
        logger.exception("redis set reminders failed for %s", phone)

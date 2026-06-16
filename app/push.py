"""Envio de push web pra Lu (Fase 3).

Quando um lead novo é fechado, manda uma notificação no navegador de quem
clicou "Ativar notificações" no painel. Usa o protocolo Web Push (VAPID).

Se as chaves VAPID não estiverem configuradas, o push fica **desligado** —
não levanta erro, só não envia (o aviso no WhatsApp da Lu segue normal).
"""

from __future__ import annotations

import asyncio
import json
import logging

from pywebpush import WebPushException, webpush
from sqlalchemy import delete, select

from app.config import settings
from app.database import SessionLocal
from app.models import PushSubscription

logger = logging.getLogger(__name__)


def push_enabled() -> bool:
    """True só se as chaves VAPID estiverem configuradas."""
    return bool(settings.vapid_public_key and settings.vapid_private_key)


def _send_one(sub: PushSubscription, payload: str) -> None:
    """Envio bloqueante (pywebpush usa `requests`) — roda em thread."""
    webpush(
        subscription_info={
            "endpoint": sub.endpoint,
            "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
        },
        data=payload,
        vapid_private_key=settings.vapid_private_key,
        vapid_claims={"sub": settings.vapid_subject},
    )


async def _dispatch(subs: list[PushSubscription], payload: str) -> tuple[int, list[str]]:
    """Envia o `payload` a cada inscrição. Sem banco — testável isolado.

    Returns:
        (quantas enviaram com sucesso, endpoints expirados a remover).
    """
    sent = 0
    expired: list[str] = []

    for sub in subs:
        try:
            await asyncio.to_thread(_send_one, sub, payload)
            sent += 1
        except WebPushException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (404, 410):
                expired.append(sub.endpoint)  # inscrição morta — limpar
            else:
                logger.warning("push falhou (status=%s): %s", status, exc)
        except Exception:
            logger.exception("push: erro inesperado p/ %s", sub.endpoint[:40])

    return sent, expired


async def send_push_to_all(title: str, body: str, url: str = "/") -> int:
    """Envia o aviso a TODAS as inscrições. Remove as expiradas (404/410).

    Returns:
        Quantas notificações foram enviadas com sucesso.
    """
    if not push_enabled():
        logger.info("push desligado (sem VAPID) — pulando aviso")
        return 0

    async with SessionLocal() as db:
        subs = (await db.execute(select(PushSubscription))).scalars().all()

    if not subs:
        return 0

    payload = json.dumps({"title": title, "body": body, "url": url})
    sent, expired = await _dispatch(list(subs), payload)

    if expired:
        async with SessionLocal() as db:
            await db.execute(
                delete(PushSubscription).where(
                    PushSubscription.endpoint.in_(expired)
                )
            )
            await db.commit()
        logger.info("push: removidas %d inscrições expiradas", len(expired))

    return sent

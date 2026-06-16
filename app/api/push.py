"""Rota /api/push — inscrição de notificações web (Fase 3).

O painel (via server action do Next.js, que guarda a X-API-Key no servidor)
manda a inscrição do navegador da Lu pra cá. A chave VAPID **pública** sai pelo
/api/config (não é segredo). O envio em si fica em `app/push.py`.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select

from app.api.auth import require_api_key
from app.database import SessionLocal
from app.models import PushSubscription

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/push",
    tags=["push"],
    dependencies=[Depends(require_api_key)],
)


class PushKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscribeIn(BaseModel):
    """Formato do `PushSubscription.toJSON()` do navegador."""

    endpoint: str
    keys: PushKeys


@router.post("/subscribe")
async def subscribe(payload: PushSubscribeIn) -> dict[str, str]:
    """Guarda (ou atualiza) a inscrição de push da Lu. Idempotente por endpoint."""
    async with SessionLocal() as db:
        existing = (
            await db.execute(
                select(PushSubscription).where(
                    PushSubscription.endpoint == payload.endpoint
                )
            )
        ).scalar_one_or_none()

        if existing is not None:
            existing.p256dh = payload.keys.p256dh
            existing.auth = payload.keys.auth
        else:
            db.add(
                PushSubscription(
                    endpoint=payload.endpoint,
                    p256dh=payload.keys.p256dh,
                    auth=payload.keys.auth,
                )
            )
        await db.commit()

    logger.info("push: inscrição registrada (%s...)", payload.endpoint[:40])
    return {"status": "ok"}

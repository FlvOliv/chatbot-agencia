"""Rotas /api/dashboard — métricas agregadas pro painel principal do CRM."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_api_key
from app.api.schemas import DashboardMetrics
from app.database import get_session
from app.models import Conversation, Lead, Reserva

router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(require_api_key)],
)


@router.get("/metrics", response_model=DashboardMetrics)
async def get_dashboard_metrics(
    db: AsyncSession = Depends(get_session),
) -> DashboardMetrics:
    """Métricas agregadas para o dashboard principal do CRM."""
    now = datetime.now(timezone.utc)
    start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_week = start_today - timedelta(days=7)
    cutoff_active = now - timedelta(hours=24)

    leads_today = (
        await db.execute(
            select(func.count(Lead.id)).where(Lead.created_at >= start_today)
        )
    ).scalar_one()

    leads_week = (
        await db.execute(
            select(func.count(Lead.id)).where(Lead.created_at >= start_week)
        )
    ).scalar_one()

    active_conversations = (
        await db.execute(
            select(func.count(func.distinct(Conversation.phone))).where(
                Conversation.created_at >= cutoff_active
            )
        )
    ).scalar_one()

    pending = (
        await db.execute(
            select(func.count(Lead.id)).where(
                Lead.lead_temp.in_(["quente", "urgente"])
            )
        )
    ).scalar_one()

    reservas_ativas = (
        await db.execute(
            select(func.count(Reserva.id)).where(Reserva.status == "ativa")
        )
    ).scalar_one()

    temp_rows = await db.execute(
        select(Lead.lead_temp, func.count(Lead.id)).group_by(Lead.lead_temp)
    )
    by_temp: dict[str, int] = {"frio": 0, "morno": 0, "quente": 0, "urgente": 0}
    for temp, count in temp_rows.all():
        if temp in by_temp:
            by_temp[temp] = int(count or 0)

    return DashboardMetrics(
        leads_today=int(leads_today or 0),
        leads_week=int(leads_week or 0),
        active_conversations=int(active_conversations or 0),
        pending_for_lu=int(pending or 0),
        reservas_ativas=int(reservas_ativas or 0),
        by_temperature=by_temp,
    )

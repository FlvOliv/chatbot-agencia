"""Rotas /api/dashboard — métricas agregadas pro painel principal do CRM."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_api_key
from app.api.schemas import (
    ConversionRate,
    DailyCount,
    DashboardInsights,
    DashboardMetrics,
    HourlyBucket,
    TopDestination,
)
from app.database import SessionLocal, get_session
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


# ---------------------------------------------------------------------------
# Insights — séries temporais p/ Painel de Insights da Malu
# ---------------------------------------------------------------------------
def _classify_provider(model_used: str | None) -> str:
    """Mapeia o campo `model_used` da Conversation pra um provider canônico.

    "gemini-*" -> "gemini", "llama*"/"groq*" -> "groq", resto/None -> "unknown".
    """
    if not model_used:
        return "unknown"
    name = model_used.lower()
    if name.startswith("gemini"):
        return "gemini"
    if name.startswith("llama") or name.startswith("groq"):
        return "groq"
    return "unknown"


async def _conversations_per_day(start: datetime) -> dict[date, int]:
    # "Uma conversa do dia = ao menos 1 msg do cliente" → distinct phones/dia.
    # Cada helper abre a própria sessão: AsyncSession do SQLAlchemy não
    # suporta uso concorrente, então asyncio.gather sobre uma única sessão
    # quebra. Sessões independentes pegam connections distintas do pool.
    day = func.date_trunc("day", Conversation.created_at)
    async with SessionLocal() as session:
        rows = await session.execute(
            select(day.label("d"), func.count(func.distinct(Conversation.phone)))
            .where(Conversation.created_at >= start, Conversation.role == "user")
            .group_by(day)
        )
        out: dict[date, int] = {}
        for d, c in rows.all():
            if d is None:
                continue
            out[d.date() if isinstance(d, datetime) else d] = int(c or 0)
        return out


async def _leads_per_day(start: datetime) -> dict[date, int]:
    day = func.date_trunc("day", Lead.created_at)
    async with SessionLocal() as session:
        rows = await session.execute(
            select(day.label("d"), func.count(Lead.id))
            .where(Lead.created_at >= start)
            .group_by(day)
        )
        out: dict[date, int] = {}
        for d, c in rows.all():
            if d is None:
                continue
            out[d.date() if isinstance(d, datetime) else d] = int(c or 0)
        return out


async def _top_destinations_raw(start: datetime) -> list[tuple[str, int]]:
    async with SessionLocal() as session:
        rows = await session.execute(
            select(Lead.destination, func.count(Lead.id).label("c"))
            .where(
                Lead.created_at >= start,
                Lead.destination.is_not(None),
                Lead.destination != "",
            )
            .group_by(Lead.destination)
            .order_by(func.count(Lead.id).desc())
            .limit(5)
        )
        return [(str(dest), int(c or 0)) for dest, c in rows.all()]


async def _hourly_distribution(start: datetime) -> dict[int, int]:
    hour_expr = func.extract("hour", Conversation.created_at)
    async with SessionLocal() as session:
        rows = await session.execute(
            select(hour_expr.label("h"), func.count(Conversation.id))
            .where(Conversation.created_at >= start, Conversation.role == "user")
            .group_by(hour_expr)
        )
        out: dict[int, int] = {}
        for h, c in rows.all():
            if h is None:
                continue
            out[int(h)] = int(c or 0)
        return out


async def _conversion_inputs(start: datetime) -> tuple[int, int]:
    async with SessionLocal() as session:
        convs = (
            await session.execute(
                select(func.count(func.distinct(Conversation.phone))).where(
                    Conversation.created_at >= start, Conversation.role == "user"
                )
            )
        ).scalar_one()
        leads = (
            await session.execute(
                select(func.count(Lead.id)).where(Lead.created_at >= start)
            )
        ).scalar_one()
        return int(convs or 0), int(leads or 0)


async def _ai_provider_rows(start: datetime) -> list[tuple[str | None, int]]:
    async with SessionLocal() as session:
        rows = await session.execute(
            select(Conversation.model_used, func.count(Conversation.id))
            .where(
                Conversation.created_at >= start,
                Conversation.role == "assistant",
            )
            .group_by(Conversation.model_used)
        )
        return [(m, int(c or 0)) for m, c in rows.all()]


@router.get("/insights", response_model=DashboardInsights)
async def get_dashboard_insights(
    days: int = Query(default=7, ge=1, le=90),
) -> DashboardInsights:
    """Insights agregados (séries temporais, top destinos, conversão, etc.).

    Janela: últimos N dias (default 7). Todas as queries rodam em paralelo
    via asyncio.gather — cada helper abre sua própria AsyncSession para
    evitar contenção (sessões SQLAlchemy não são thread/coroutine-safe).
    """
    now = datetime.now(timezone.utc)
    start_day = (now - timedelta(days=days - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    (
        convs_per_day,
        leads_per_day_map,
        top_dest_rows,
        hourly_map,
        conv_pair,
        provider_rows,
    ) = await asyncio.gather(
        _conversations_per_day(start_day),
        _leads_per_day(start_day),
        _top_destinations_raw(start_day),
        _hourly_distribution(start_day),
        _conversion_inputs(start_day),
        _ai_provider_rows(start_day),
    )

    # Preenche todos os dias do range (mesmo com count=0).
    day_range: list[date] = [
        start_day.date() + timedelta(days=i) for i in range(days)
    ]

    conversations_per_day = [
        DailyCount(date=d, count=convs_per_day.get(d, 0)) for d in day_range
    ]
    leads_per_day = [
        DailyCount(date=d, count=leads_per_day_map.get(d, 0)) for d in day_range
    ]

    # Top destinos: pct sobre soma dos próprios top N (não sobre todos os leads).
    total_top = sum(c for _, c in top_dest_rows) or 0
    top_destinations = [
        TopDestination(
            destination=dest,
            count=c,
            pct=(c / total_top) if total_top > 0 else 0.0,
        )
        for dest, c in top_dest_rows
    ]

    hourly_distribution = [
        HourlyBucket(hour=h, count=hourly_map.get(h, 0)) for h in range(24)
    ]

    conversations_started, leads_generated = conv_pair
    rate = (
        leads_generated / conversations_started
        if conversations_started > 0
        else 0.0
    )
    conversion_rate = ConversionRate(
        conversations_started=conversations_started,
        leads_generated=leads_generated,
        rate=rate,
    )

    ai_breakdown: dict[str, int] = {"gemini": 0, "groq": 0, "unknown": 0}
    for model_used, c in provider_rows:
        bucket = _classify_provider(model_used)
        ai_breakdown[bucket] = ai_breakdown.get(bucket, 0) + c

    return DashboardInsights(
        range_days=days,
        generated_at=now,
        conversations_per_day=conversations_per_day,
        leads_per_day=leads_per_day,
        top_destinations=top_destinations,
        hourly_distribution=hourly_distribution,
        conversion_rate=conversion_rate,
        ai_provider_breakdown=ai_breakdown,
    )

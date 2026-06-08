"""Rotas /api/leads — lista paginada com filtros e detalhe."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_api_key
from app.api.schemas import (
    ClienteOut,
    LeadDetail,
    LeadListItem,
    LeadListResponse,
    LeadOut,
)
from app.database import get_session
from app.models import Cliente, Conversation, Lead

router = APIRouter(
    prefix="/leads",
    tags=["leads"],
    dependencies=[Depends(require_api_key)],
)


@router.get("", response_model=LeadListResponse)
async def list_leads(
    temp: str | None = Query(default=None, description="Filtro: frio|morno|quente|urgente"),
    q: str | None = Query(default=None, description="Busca: nome ou telefone"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_session),
) -> LeadListResponse:
    """Lista paginada de leads, com filtro opcional de temperatura e busca."""
    base = select(Lead)

    if temp and temp.lower() != "all":
        base = base.where(Lead.lead_temp == temp.lower())

    if q:
        like = f"%{q.strip()}%"
        base = base.where(or_(Lead.phone.ilike(like), Lead.name.ilike(like)))

    # Contagem total (antes da paginação)
    total_stmt = select(func.count()).select_from(base.subquery())
    total = (await db.execute(total_stmt)).scalar_one()

    # Paginação
    offset = (page - 1) * page_size
    rows = await db.execute(
        base.order_by(Lead.created_at.desc()).limit(page_size).offset(offset)
    )
    items = [LeadListItem.model_validate(lead) for lead in rows.scalars().all()]

    return LeadListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{phone}", response_model=LeadDetail)
async def get_lead_by_phone(
    phone: str,
    db: AsyncSession = Depends(get_session),
) -> LeadDetail:
    """Detalhe de um lead pelo phone (chave natural)."""
    lead_row = await db.execute(select(Lead).where(Lead.phone == phone))
    lead = lead_row.scalar_one_or_none()
    if lead is None:
        raise HTTPException(status_code=404, detail="lead não encontrado")

    cliente_row = await db.execute(select(Cliente).where(Cliente.phone == phone))
    cliente = cliente_row.scalar_one_or_none()

    count_stmt = select(func.count(Conversation.id)).where(Conversation.phone == phone)
    count = (await db.execute(count_stmt)).scalar_one()

    return LeadDetail(
        lead=LeadOut.model_validate(lead),
        cliente=ClienteOut.model_validate(cliente) if cliente else None,
        conversation_count=int(count or 0),
    )

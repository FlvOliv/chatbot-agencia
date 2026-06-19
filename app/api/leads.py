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
    sort: str = Query(default="recent", description="Ordenação: recent (mais novo) | oldest (mais antigo)"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_session),
) -> LeadListResponse:
    """Lista paginada de leads, com filtro de temperatura, busca e ordenação."""
    base = select(Lead)

    if temp and temp.lower() != "all":
        base = base.where(Lead.lead_temp == temp.lower())

    if q:
        like = f"%{q.strip()}%"
        base = base.where(or_(Lead.phone.ilike(like), Lead.name.ilike(like)))

    # Contagem total (antes da paginação)
    total_stmt = select(func.count()).select_from(base.subquery())
    total = (await db.execute(total_stmt)).scalar_one()

    # Ordenação por data (default: mais novo primeiro)
    order = Lead.created_at.asc() if sort == "oldest" else Lead.created_at.desc()

    # Paginação
    offset = (page - 1) * page_size
    rows = await db.execute(
        base.order_by(order).limit(page_size).offset(offset)
    )
    items = [LeadListItem.model_validate(lead) for lead in rows.scalars().all()]

    return LeadListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


async def _build_lead_detail(lead: Lead, db: AsyncSession) -> LeadDetail:
    """Monta o LeadDetail (lead + cliente + contagem de mensagens)."""
    cliente_row = await db.execute(select(Cliente).where(Cliente.phone == lead.phone))
    cliente = cliente_row.scalar_one_or_none()

    count_stmt = select(func.count(Conversation.id)).where(
        Conversation.phone == lead.phone
    )
    count = (await db.execute(count_stmt)).scalar_one()

    return LeadDetail(
        lead=LeadOut.model_validate(lead),
        cliente=ClienteOut.model_validate(cliente) if cliente else None,
        conversation_count=int(count or 0),
    )


@router.get("/by-numero/{numero}", response_model=LeadDetail)
async def get_lead_by_numero(
    numero: int,
    db: AsyncSession = Depends(get_session),
) -> LeadDetail:
    """Detalhe de UMA cotação específica pelo seu número (#1001...)."""
    lead_row = await db.execute(select(Lead).where(Lead.numero == numero))
    lead = lead_row.scalar_one_or_none()
    if lead is None:
        raise HTTPException(status_code=404, detail="cotação não encontrada")
    return await _build_lead_detail(lead, db)


@router.get("/{phone}", response_model=LeadDetail)
async def get_lead_by_phone(
    phone: str,
    db: AsyncSession = Depends(get_session),
) -> LeadDetail:
    """Detalhe da cotação MAIS RECENTE de um telefone.

    Como o mesmo cliente pode ter várias cotações, devolve a última (usada no
    painel lateral da conversa). Pra uma cotação específica, use /by-numero.
    """
    lead_row = await db.execute(
        select(Lead)
        .where(Lead.phone == phone)
        .order_by(Lead.created_at.desc())
        .limit(1)
    )
    lead = lead_row.scalar_one_or_none()
    if lead is None:
        raise HTTPException(status_code=404, detail="lead não encontrado")
    return await _build_lead_detail(lead, db)

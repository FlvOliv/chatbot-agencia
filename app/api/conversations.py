"""Rotas /api/conversations — lista de conversas e histórico por phone."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_api_key
from app.api.schemas import ConversationDetail, ConversationSummary, MessageOut
from app.database import get_session
from app.models import Cliente, Conversation, Lead

router = APIRouter(
    prefix="/conversations",
    tags=["conversations"],
    dependencies=[Depends(require_api_key)],
)


@router.get("", response_model=list[ConversationSummary])
async def list_conversations(
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_session),
) -> list[ConversationSummary]:
    """Lista as conversas mais recentes (1 por phone), ordenadas pela última mensagem."""
    # Subquery: última mensagem por phone
    last_msg_subq = (
        select(
            Conversation.phone,
            func.max(Conversation.created_at).label("last_at"),
            func.count(Conversation.id).label("msg_count"),
        )
        .group_by(Conversation.phone)
        .subquery()
    )

    rows = await db.execute(
        select(
            last_msg_subq.c.phone,
            last_msg_subq.c.last_at,
            last_msg_subq.c.msg_count,
        )
        .order_by(last_msg_subq.c.last_at.desc())
        .limit(limit)
    )
    summaries: list[ConversationSummary] = []
    for phone, last_at, msg_count in rows.all():
        # Preview da última mensagem
        last_content_row = await db.execute(
            select(Conversation.content)
            .where(Conversation.phone == phone, Conversation.created_at == last_at)
            .limit(1)
        )
        content = last_content_row.scalar_one_or_none() or ""
        # Nome do cliente
        cliente_row = await db.execute(select(Cliente).where(Cliente.phone == phone))
        cliente = cliente_row.scalar_one_or_none()
        # Temperatura do lead (se houver)
        lead_row = await db.execute(
            select(Lead.lead_temp).where(Lead.phone == phone).limit(1)
        )
        lead_temp = lead_row.scalar_one_or_none()

        summaries.append(
            ConversationSummary(
                phone=phone,
                customer_name=cliente.display_name if cliente else None,
                last_message_at=last_at,
                last_message_preview=(content or "")[:120],
                message_count=int(msg_count or 0),
                lead_temp=lead_temp,
            )
        )
    return summaries


@router.get("/{phone}", response_model=ConversationDetail)
async def get_conversation(
    phone: str,
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_session),
) -> ConversationDetail:
    """Histórico completo (ou últimas N mensagens) de uma conversa."""
    rows = await db.execute(
        select(Conversation)
        .where(Conversation.phone == phone)
        .order_by(Conversation.created_at.asc())
        .limit(limit)
    )
    messages = list(rows.scalars().all())
    if not messages:
        raise HTTPException(status_code=404, detail="conversa não encontrada")

    cliente_row = await db.execute(select(Cliente).where(Cliente.phone == phone))
    cliente = cliente_row.scalar_one_or_none()

    return ConversationDetail(
        phone=phone,
        customer_name=cliente.display_name if cliente else None,
        messages=[MessageOut.model_validate(m) for m in messages],
    )

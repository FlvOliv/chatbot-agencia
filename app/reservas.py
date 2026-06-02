"""Consulta de reservas dos clientes.

A Malu usa isto na primeira mensagem da sessão pra decidir o caminho:
- Cliente sem reserva ativa → fluxo normal de coleta
- Cliente com reserva ativa → oferece transferência direta pra Lu
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from app.models import Reserva

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def get_reservas_ativas(
    phone: str,
    db: AsyncSession,
) -> list[Reserva]:
    """Retorna todas as reservas com status='ativa' do cliente."""
    result = await db.execute(
        select(Reserva)
        .where(Reserva.phone == phone, Reserva.status == "ativa")
        .order_by(Reserva.created_at.desc())
    )
    return list(result.scalars().all())


async def has_reserva_ativa(phone: str, db: AsyncSession) -> bool:
    """Atalho: True se o cliente tem ao menos uma reserva ativa."""
    result = await db.execute(
        select(func.count(Reserva.id)).where(
            Reserva.phone == phone,
            Reserva.status == "ativa",
        )
    )
    return (result.scalar() or 0) > 0

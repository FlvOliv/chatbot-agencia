"""Gestão de clientes — get/create + atualização de nome.

Cliente vs Lead:
- Cliente: pessoa identificada por um número WhatsApp. Identidade duradoura.
- Lead: intenção de viagem capturada. Um cliente pode ter N leads.

Esta camada é independente do fluxo de IA — só toca a tabela `clientes`.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models import Cliente

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def get_cliente(phone: str, db: AsyncSession) -> Cliente | None:
    """Busca cliente por phone. None se não existe."""
    result = await db.execute(select(Cliente).where(Cliente.phone == phone))
    return result.scalar_one_or_none()


async def get_or_create_cliente(
    phone: str,
    profile_name: str | None,
    db: AsyncSession,
) -> Cliente:
    """Retorna o cliente existente, ou cria um novo.

    Na criação, `profile_name` vira o `name` inicial (pra Malu já cumprimentar
    pelo nome). O cliente pode corrigir depois, e a Malu atualiza via briefing.

    Em concorrência, usa INSERT ... ON CONFLICT DO NOTHING + SELECT pra
    garantir idempotência.
    """
    stmt = (
        pg_insert(Cliente)
        .values(
            phone=phone,
            profile_name=profile_name,
            name=profile_name,  # fallback inicial
        )
        .on_conflict_do_nothing(index_elements=["phone"])
    )
    await db.execute(stmt)
    await db.flush()

    result = await db.execute(select(Cliente).where(Cliente.phone == phone))
    cliente = result.scalar_one()
    return cliente


async def update_preferred_name(
    phone: str,
    new_name: str,
    db: AsyncSession,
) -> None:
    """Atualiza o nome preferido do cliente. Não toca em profile_name."""
    cleaned = (new_name or "").strip()
    if not cleaned:
        return
    cliente = await get_cliente(phone, db)
    if cliente is None:
        logger.warning("update_preferred_name: cliente %s não existe", phone)
        return
    if cliente.name == cleaned:
        return  # nada a fazer
    cliente.name = cleaned
    await db.flush()

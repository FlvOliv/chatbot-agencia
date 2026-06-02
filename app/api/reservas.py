"""Rotas /api/reservas — lista e criação manual de reservas pela Lu."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_api_key
from app.api.schemas import ReservaCreate, ReservaOut
from app.database import get_session
from app.models import Cliente, Reserva

router = APIRouter(
    prefix="/reservas",
    tags=["reservas"],
    dependencies=[Depends(require_api_key)],
)


@router.get("", response_model=list[ReservaOut])
async def list_reservas(
    status: str | None = Query(default=None, description="Filtro: ativa|encerrada|cancelada"),
    db: AsyncSession = Depends(get_session),
) -> list[ReservaOut]:
    """Lista todas as reservas, ordenadas por created_at desc."""
    stmt = select(Reserva).order_by(Reserva.created_at.desc())
    if status:
        stmt = stmt.where(Reserva.status == status.lower())
    rows = await db.execute(stmt)
    return [ReservaOut.model_validate(r) for r in rows.scalars().all()]


@router.post("", response_model=ReservaOut, status_code=201)
async def create_reserva(
    payload: ReservaCreate,
    db: AsyncSession = Depends(get_session),
) -> ReservaOut:
    """Cria uma nova reserva — exige que o cliente já exista (FK)."""
    cliente_row = await db.execute(
        select(Cliente).where(Cliente.phone == payload.phone)
    )
    cliente = cliente_row.scalar_one_or_none()
    if cliente is None:
        raise HTTPException(
            status_code=400,
            detail=f"cliente {payload.phone} não existe — cadastre antes",
        )

    reserva = Reserva(
        phone=payload.phone,
        codigo_reserva=payload.codigo_reserva,
        destino=payload.destino,
        data_viagem=payload.data_viagem,
        status=payload.status,
        observacoes=payload.observacoes,
    )
    db.add(reserva)
    await db.flush()
    await db.refresh(reserva)
    return ReservaOut.model_validate(reserva)

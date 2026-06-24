"""Rotas /api/tags — catálogo de etiquetas (CRUD).

Associação tag↔cliente fica em /api/conversations/{phone}/tags/* (conversations.py).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_api_key
from app.api.schemas import TagIn, TagOut
from app.database import get_session
from app.models import Tag

router = APIRouter(
    prefix="/tags",
    tags=["tags"],
    dependencies=[Depends(require_api_key)],
)


@router.get("", response_model=list[TagOut])
async def list_tags(db: AsyncSession = Depends(get_session)) -> list[Tag]:
    rows = await db.execute(select(Tag).order_by(Tag.name))
    return list(rows.scalars().all())


@router.post("", response_model=TagOut, status_code=201)
async def create_tag(body: TagIn, db: AsyncSession = Depends(get_session)) -> Tag:
    tag = Tag(name=body.name.strip(), color=body.color)
    db.add(tag)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Tag já existe com esse nome.")
    await db.refresh(tag)
    return tag



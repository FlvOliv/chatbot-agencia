"""Rotas /api/tags — catálogo de etiquetas (CRUD).

Associação tag↔cliente fica em /api/conversations/{phone}/tags/* (conversations.py).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
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


@router.delete("/{tag_id}")
async def delete_tag(
    tag_id: str, db: AsyncSession = Depends(get_session)
) -> Response:
    """Remove a etiqueta do catálogo (idempotente).

    O FK `cliente_tags.tag_id` é ON DELETE CASCADE → a tag some de todas as
    conversas automaticamente.
    """
    try:
        tid = uuid.UUID(tag_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="tag_id inválido.")

    tag = await db.get(Tag, tid)
    if tag:
        await db.delete(tag)
        await db.commit()
    return Response(status_code=204)



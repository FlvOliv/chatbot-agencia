"""Rotas /api/conversations — lista de conversas e histórico por phone."""

from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from pydantic import BaseModel, Field

from app.api.auth import require_api_key
from app.api.schemas import ConversationDetail, ConversationSummary, MessageOut, TagOut
from app.audioconv import transcode_to_mp3, transcode_to_ogg_opus
from app.database import get_session
from app.models import Cliente, ClienteTag, Conversation, Lead, Tag
from app.storage import signed_url, upload_audio
from app.session import (
    STATE_TRANSFERRED,
    clear_state,
    get_state,
    get_states,
    set_state,
)
from app.whatsapp import send_audio, send_message, upload_media

router = APIRouter(
    prefix="/conversations",
    tags=["conversations"],
    dependencies=[Depends(require_api_key)],
)


@router.get("", response_model=list[ConversationSummary])
async def list_conversations(
    limit: int = Query(default=50, ge=1, le=200),
    q: str | None = Query(default=None, description="Busca: nome ou telefone"),
    tag_id: uuid.UUID | None = Query(
        default=None, description="Filtra pela etiqueta (server-side, antes do limit)"
    ),
    db: AsyncSession = Depends(get_session),
) -> list[ConversationSummary]:
    """Lista as conversas mais recentes (1 por phone), ordenadas pela última mensagem.

    Preview, cliente, temperatura, tags e estado são carregados em LOTE (3 queries
    + 1 MGET no Redis) — sem o N+1 de 1 conversa por 4 round-trips.
    """
    # Subquery: última mensagem por phone (last_at + contagem)
    last_msg_subq = (
        select(
            Conversation.phone,
            func.max(Conversation.created_at).label("last_at"),
            func.count(Conversation.id).label("msg_count"),
        )
        .group_by(Conversation.phone)
        .subquery()
    )

    stmt = select(
        last_msg_subq.c.phone,
        last_msg_subq.c.last_at,
        last_msg_subq.c.msg_count,
    )

    # Busca por nome (cliente) ou telefone
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.outerjoin(
            Cliente, Cliente.phone == last_msg_subq.c.phone
        ).where(
            or_(
                last_msg_subq.c.phone.ilike(like),
                Cliente.name.ilike(like),
                Cliente.profile_name.ilike(like),
            )
        )

    # Filtro por etiqueta — JOIN na associação ANTES do limit (filtro REAL no banco,
    # não no top-50 já carregado). PK composta (phone, tag_id) → no máx. 1 match por
    # phone, sem duplicar linhas.
    if tag_id is not None:
        stmt = stmt.join(
            ClienteTag, ClienteTag.cliente_phone == last_msg_subq.c.phone
        ).where(ClienteTag.tag_id == tag_id)

    rows_all = (
        await db.execute(stmt.order_by(last_msg_subq.c.last_at.desc()).limit(limit))
    ).all()
    if not rows_all:
        return []

    phones = [r[0] for r in rows_all]

    # Preview: última mensagem de cada phone (DISTINCT ON — 1 query pro lote todo)
    content_rows = await db.execute(
        select(Conversation.phone, Conversation.content)
        .where(Conversation.phone.in_(phones))
        .order_by(Conversation.phone, Conversation.created_at.desc())
        .distinct(Conversation.phone)
    )
    content_by_phone = {p: c for p, c in content_rows.all()}

    # Cliente de cada phone (1 query)
    cliente_rows = await db.execute(select(Cliente).where(Cliente.phone.in_(phones)))
    cliente_by_phone = {c.phone: c for c in cliente_rows.scalars().all()}

    # Temperatura: a cotação MAIS RECENTE de cada phone (DISTINCT ON — 1 query)
    lead_rows = await db.execute(
        select(Lead.phone, Lead.lead_temp)
        .where(Lead.phone.in_(phones))
        .order_by(Lead.phone, Lead.created_at.desc())
        .distinct(Lead.phone)
    )
    lead_temp_by_phone = {p: t for p, t in lead_rows.all()}

    # Tags de cada phone (1 query — já era sem N+1)
    tags_by_phone: dict[str, list[Tag]] = {}
    tag_rows = await db.execute(
        select(ClienteTag.cliente_phone, Tag)
        .join(Tag, Tag.id == ClienteTag.tag_id)
        .where(ClienteTag.cliente_phone.in_(phones))
    )
    for cp, tag in tag_rows.all():
        tags_by_phone.setdefault(cp, []).append(tag)

    # Estado do bot via MGET — 1 round-trip Redis pro lote (antes: 1 por linha)
    states = await get_states(phones)

    summaries: list[ConversationSummary] = []
    for phone, last_at, msg_count in rows_all:
        cliente = cliente_by_phone.get(phone)
        summaries.append(
            ConversationSummary(
                phone=phone,
                customer_name=cliente.display_name if cliente else None,
                last_message_at=last_at,
                last_message_preview=(content_by_phone.get(phone) or "")[:120],
                message_count=int(msg_count or 0),
                lead_temp=lead_temp_by_phone.get(phone),
                bot_paused=(states.get(phone) == STATE_TRANSFERRED),
                tags=[TagOut.model_validate(t) for t in tags_by_phone.get(phone, [])],
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

    # Mensagens de voz têm media_path → gera o link assinado pro player do painel.
    out: list[MessageOut] = []
    for m in messages:
        mo = MessageOut.model_validate(m)
        if m.media_path:
            mo.audio_url = await signed_url(m.media_path)
        out.append(mo)

    return ConversationDetail(
        phone=phone,
        customer_name=cliente.display_name if cliente else None,
        messages=out,
    )


# ---------------------------------------------------------------------------
# Atendimento humano (Caminho A) — assumir / devolver / responder
# ---------------------------------------------------------------------------
class StateOut(BaseModel):
    phone: str
    bot_paused: bool


class ReplyIn(BaseModel):
    text: str = Field(min_length=1, max_length=4096)


class ReplyOut(BaseModel):
    phone: str
    sent: bool
    error: str | None = None


@router.get("/{phone}/state", response_model=StateOut)
async def conversation_state(phone: str) -> StateOut:
    """Diz se o bot está pausado (humano assumiu) nessa conversa."""
    state = await get_state(phone)
    return StateOut(phone=phone, bot_paused=state == STATE_TRANSFERRED)


@router.post("/{phone}/takeover", response_model=StateOut)
async def takeover(phone: str) -> StateOut:
    """A Lu assume a conversa — a Malu para de responder automaticamente."""
    await set_state(phone, STATE_TRANSFERRED)
    return StateOut(phone=phone, bot_paused=True)


@router.post("/{phone}/release", response_model=StateOut)
async def release(phone: str) -> StateOut:
    """Devolve a conversa pra Malu — o bot volta a responder."""
    await clear_state(phone)
    return StateOut(phone=phone, bot_paused=False)


@router.post("/{phone}/reply", response_model=ReplyOut)
async def human_reply(
    phone: str,
    body: ReplyIn,
    db: AsyncSession = Depends(get_session),
) -> ReplyOut:
    """A Lu manda uma mensagem pro cliente PELO número da Malu.

    Garante o estado 'transferido' (bot calado), grava a mensagem no
    histórico e tenta enviar pela Cloud API. Requer número WhatsApp válido
    pra entregar de verdade.
    """
    await set_state(phone, STATE_TRANSFERRED)

    # Grava a mensagem da Lu no histórico (marcada como 'human')
    db.add(
        Conversation(
            phone=phone,
            role="assistant",
            content=body.text,
            model_used="human",
        )
    )
    await db.commit()

    sent = False
    error: str | None = None
    try:
        sent = await send_message(phone, body.text)
        if not sent:
            error = "Meta recusou o envio (número/permissão). Veja os logs."
    except Exception as exc:  # noqa: BLE001
        error = f"Falha no envio: {exc}"

    return ReplyOut(phone=phone, sent=sent, error=error)


@router.post("/{phone}/reply-audio", response_model=ReplyOut)
async def human_reply_audio(
    phone: str,
    audio: UploadFile = File(...),
    db: AsyncSession = Depends(get_session),
) -> ReplyOut:
    """A Lu grava uma nota de voz no painel e manda pro cliente.

    Recebe o áudio do navegador (webm/mp4), recodifica em paralelo pra OGG/Opus
    (nota de voz no WhatsApp) e MP3 (player do painel, toca em qualquer
    navegador). Guarda o MP3 no Storage, grava no histórico e envia o OGG pela
    Cloud API. Garante o estado 'transferido' (bot calado).
    """
    raw = await audio.read()
    if not raw:
        raise HTTPException(status_code=422, detail="Áudio vazio.")

    await set_state(phone, STATE_TRANSFERRED)

    # 2 transcodes em paralelo: OGG (envio) + MP3 (painel)
    ogg, mp3 = await asyncio.gather(
        transcode_to_ogg_opus(raw),
        transcode_to_mp3(raw),
    )

    # Guarda o MP3 pro player do painel (best-effort — não bloqueia o envio)
    media_path = await upload_audio(phone, mp3, "audio/mpeg") if mp3 else None

    # Grava no histórico (marcada como 'human')
    db.add(
        Conversation(
            phone=phone,
            role="assistant",
            content="🎤 Áudio",
            model_used="human",
            media_path=media_path,
        )
    )
    await db.commit()

    # Envia o OGG/Opus pelo WhatsApp (2 passos: upload → send)
    sent = False
    error: str | None = None
    if not ogg:
        error = "Não consegui converter o áudio (ffmpeg). Veja os logs."
    else:
        try:
            media_id = await upload_media(ogg, "audio/ogg", "nota.ogg")
            if media_id:
                sent = await send_audio(phone, media_id)
            if not sent:
                error = "Meta recusou o envio do áudio (número/permissão). Veja os logs."
        except Exception as exc:  # noqa: BLE001
            error = f"Falha no envio do áudio: {exc}"

    return ReplyOut(phone=phone, sent=sent, error=error)


# ---------------------------------------------------------------------------
# Tags da conversa — associação cliente ↔ tag
# ---------------------------------------------------------------------------

@router.post("/{phone}/tags/{tag_id}", response_model=TagOut, status_code=201)
async def add_tag(
    phone: str,
    tag_id: str,
    db: AsyncSession = Depends(get_session),
) -> Tag:
    """Associa uma etiqueta ao cliente da conversa (idempotente)."""
    try:
        tid = uuid.UUID(tag_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="tag_id inválido.")

    tag = await db.get(Tag, tid)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag não encontrada.")

    existing = await db.get(ClienteTag, (phone, tid))
    if not existing:
        db.add(ClienteTag(cliente_phone=phone, tag_id=tid))
        await db.commit()
    return tag


@router.delete("/{phone}/tags/{tag_id}")
async def remove_tag(
    phone: str,
    tag_id: str,
    db: AsyncSession = Depends(get_session),
) -> Response:
    """Remove a associação de uma etiqueta com o cliente (idempotente)."""
    try:
        tid = uuid.UUID(tag_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="tag_id inválido.")

    assoc = await db.get(ClienteTag, (phone, tid))
    if assoc:
        await db.delete(assoc)
        await db.commit()
    return Response(status_code=204)

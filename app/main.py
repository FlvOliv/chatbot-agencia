"""FastAPI entrypoint — webhook Meta + health check.

Fluxo (CLAUDE.md, seção "Fluxo principal de uma mensagem"):
    1. Meta envia POST /webhook
    2. Validamos a assinatura HMAC-SHA256
    3. Sempre respondemos 200 (erros logados internamente)
    4. handle_message roda em background (não bloqueia a resposta)
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from app import __version__
from app.ai import route_and_ask
from app.api import api_router
from app.briefing import (
    extract_briefing,
    extract_customer_name,
    notify_luciana,
    notify_luciana_returning_client,
    parse_lead_temp,
    save_lead,
)
from app.clientes import get_or_create_cliente, update_preferred_name
from app.commands import (
    EXIT_REPLY,
    INTENT_NOVA,
    INTENT_RESERVA,
    intent_question,
    intent_unclear_reply,
    is_exit_command,
    parse_intent,
    transferred_reply,
)
from app.config import settings
from app.database import SessionLocal, dispose_engine
from app.models import Conversation
from app.reminders import cancel_reminders, schedule_reminders
from app.reservas import has_reserva_ativa
from app.session import (
    STATE_AWAITING_INTENT,
    STATE_TRANSFERRED,
    clear_history,
    clear_state,
    close_redis,
    get_history,
    get_redis,
    get_state,
    save_history,
    set_state,
)
from app.whatsapp import (
    NON_TEXT_REPLY,
    detect_non_text_message,
    parse_incoming,
    send_message,
)

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("malu")


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    """Inicializa e finaliza recursos compartilhados."""
    logger.info("malu starting up — env=%s", settings.app_env)
    # Aquece o client Redis (não levanta se Redis estiver offline — só loga)
    try:
        client = get_redis()
        await client.ping()
        logger.info("redis OK")
    except Exception:
        logger.exception("redis ping failed on startup (continuing)")

    yield

    logger.info("malu shutting down")
    await close_redis()
    await dispose_engine()


app = FastAPI(
    title="Malu Bot — Lu Milhas & Viagens",
    version=__version__,
    lifespan=lifespan,
)

# CORS — permite o frontend CRM (Next.js) consumir as rotas /api/*
_origins = [o.strip() for o in settings.crm_cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Rotas REST do CRM (todas em /api/*, exigem X-API-Key)
app.include_router(api_router)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/health")
async def health() -> dict[str, Any]:
    """Health check — usado por Railway/load balancer."""
    return {
        "status": "ok",
        "version": __version__,
        "env": settings.app_env,
        "now": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Webhook — verificação (handshake Meta)
# ---------------------------------------------------------------------------
@app.get("/webhook")
async def webhook_verify(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
) -> PlainTextResponse:
    """Handshake da Meta: retorna o `challenge` se o token bate."""
    if hub_mode == "subscribe" and hub_verify_token == settings.wa_verify_token:
        return PlainTextResponse(hub_challenge or "", status_code=200)
    raise HTTPException(status_code=403, detail="verify token mismatch")


# ---------------------------------------------------------------------------
# Webhook — recebimento de mensagens
# ---------------------------------------------------------------------------
def _verify_signature(raw_body: bytes, signature_header: str | None) -> bool:
    """Verifica `X-Hub-Signature-256: sha256=<hex>` usando WA_APP_SECRET."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(
        settings.wa_app_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    received = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, received)


@app.post("/webhook")
async def webhook_receive(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
) -> JSONResponse:
    """Recebe mensagens da Meta.

    Sempre retorna 200 (exceto assinatura inválida → 401) — qualquer erro
    interno é logado, **nunca** propagado, para evitar que a Meta re-entregue
    a mesma mensagem várias vezes.
    """
    raw = await request.body()

    if not _verify_signature(raw, x_hub_signature_256):
        logger.warning("invalid signature on /webhook")
        raise HTTPException(status_code=401, detail="invalid signature")

    try:
        data = await request.json()
    except Exception:
        logger.exception("invalid JSON on /webhook")
        return JSONResponse({"status": "ignored"}, status_code=200)

    background_tasks.add_task(handle_message, data)
    return JSONResponse({"status": "received"}, status_code=200)


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------
async def handle_message(data: dict[str, Any]) -> None:
    """Executa o fluxo completo da Malu (descrito no CLAUDE.md).

    Ordem de decisão (early-returns no topo, IA por último):

        0. Mensagem inválida ou tipo ignorado → drop.
        1. Comando /sair → encerra sessão, sai.
        2. Estado "transferred" (Lu já assumiu) → silêncio total, sai.
        3. Identifica/cria o cliente no banco.
        4. Estado "awaiting_intent" → parse 1/2:
           a. "1" → notifica Lu, marca transferred, sai.
           b. "2" → limpa estado, segue pra IA.
           c. ambíguo → repete a pergunta, sai.
        5. Primeira mensagem da sessão E cliente tem reserva ativa →
           manda pergunta de intent (1/2), marca awaiting_intent, sai.
        6. Caminho normal: histórico → IA → resposta → briefing.
    """
    # 0) Mensagem de tipo não-texto (áudio, imagem, vídeo, etc.)
    #    Responde educadamente em vez de ficar muda. Não chama IA, não
    #    persiste no histórico Redis (cliente vai reescrever em texto).
    non_text = detect_non_text_message(data)
    if non_text is not None:
        nt_phone, nt_profile, nt_type = non_text
        logger.info(
            "non-text message type=%s from %s (profile=%r)",
            nt_type, nt_phone, nt_profile,
        )
        try:
            await send_message(nt_phone, NON_TEXT_REPLY)
        except Exception:
            logger.exception("send NON_TEXT_REPLY failed for %s", nt_phone)
        asyncio.create_task(
            _persist_conversation(
                nt_phone, f"[mensagem de {nt_type}]", NON_TEXT_REPLY, f"non-text:{nt_type}"
            )
        )
        return

    parsed = parse_incoming(data)
    if parsed is None:
        return
    phone, user_text, profile_name = parsed

    logger.info(
        "incoming from %s (profile=%r): %s",
        phone,
        profile_name,
        user_text[:120],
    )

    # 1) Comando /sair (prioridade máxima — funciona em qualquer estado)
    if is_exit_command(user_text):
        logger.info("exit command from %s — closing session", phone)
        await clear_history(phone)
        await clear_state(phone)
        await cancel_reminders(phone)
        try:
            await send_message(phone, EXIT_REPLY)
        except Exception:
            logger.exception("send EXIT_REPLY failed for %s", phone)
        asyncio.create_task(
            _persist_conversation(phone, user_text, EXIT_REPLY, "command:exit")
        )
        return

    # 2) Cliente já transferido pra Lu — Malu fica em silêncio
    state = await get_state(phone)
    if state == STATE_TRANSFERRED:
        logger.info("skipping %s — conversation transferred to Lu", phone)
        # Audit log mesmo assim (Lu pode querer ver tudo depois)
        asyncio.create_task(
            _persist_conversation(phone, user_text, "", "transferred")
        )
        return

    # 3) Identifica/atualiza o cliente (não bloqueia em falha de banco)
    customer_name: str | None = None
    try:
        async with SessionLocal() as db:
            cliente = await get_or_create_cliente(phone, profile_name, db)
            await db.commit()
            customer_name = cliente.display_name
    except Exception:
        logger.exception("get_or_create_cliente failed for %s", phone)
        customer_name = profile_name

    # 4) Em meio de awaiting_intent: parse e bifurca
    if state == STATE_AWAITING_INTENT:
        intent = parse_intent(user_text)
        if intent == INTENT_RESERVA:
            logger.info("intent=reserva from %s — transferring to Lu", phone)
            reply = transferred_reply(customer_name)
            await set_state(phone, STATE_TRANSFERRED)
            await cancel_reminders(phone)
            try:
                await send_message(phone, reply)
            except Exception:
                logger.exception("send transferred_reply failed for %s", phone)
            try:
                await notify_luciana_returning_client(phone, customer_name)
            except Exception:
                logger.exception("notify_luciana_returning_client failed for %s", phone)
            asyncio.create_task(
                _persist_conversation(phone, user_text, reply, "flow:transferred")
            )
            return

        if intent == INTENT_NOVA:
            logger.info("intent=nova from %s — proceeding to AI flow", phone)
            await clear_state(phone)
            # Cai pro fluxo normal abaixo (sem return)
        else:
            # Ambíguo — pede pra escolher de novo, mantém o estado
            logger.info("intent=ambiguous from %s — re-prompting", phone)
            reply = intent_unclear_reply()
            try:
                await send_message(phone, reply)
            except Exception:
                logger.exception("send intent_unclear_reply failed for %s", phone)
            asyncio.create_task(
                _persist_conversation(phone, user_text, reply, "flow:intent-unclear")
            )
            return

    # 5) Primeira mensagem da sessão + cliente com reserva ativa → pergunta intent
    history = await get_history(phone)
    is_first_turn = len(history) == 0

    if is_first_turn and state != STATE_AWAITING_INTENT:
        try:
            async with SessionLocal() as db:
                has_active = await has_reserva_ativa(phone, db)
        except Exception:
            logger.exception("has_reserva_ativa check failed for %s", phone)
            has_active = False  # fallback: não trava o cliente

        if has_active:
            logger.info("first turn + reserva ativa for %s — asking intent", phone)
            reply = intent_question(customer_name)
            await set_state(phone, STATE_AWAITING_INTENT)
            try:
                await send_message(phone, reply)
            except Exception:
                logger.exception("send intent_question failed for %s", phone)
            asyncio.create_task(
                _persist_conversation(phone, user_text, reply, "flow:intent-question")
            )
            return

    # 6) Fluxo normal — IA + briefing
    history.append({"role": "user", "content": user_text})
    customer_context = {"name": customer_name, "is_first_turn": is_first_turn}
    reply, model_used = await route_and_ask(history, customer_context=customer_context)
    history.append({"role": "assistant", "content": reply})

    await save_history(phone, history)

    send_task = asyncio.create_task(send_message(phone, reply))
    audit_task = asyncio.create_task(_persist_conversation(phone, user_text, reply, model_used))

    briefing = extract_briefing(reply)
    if briefing:
        temp = parse_lead_temp(briefing)
        try:
            async with SessionLocal() as db:
                await save_lead(phone, briefing, temp, db)
                briefing_name = extract_customer_name(briefing)
                if briefing_name:
                    await update_preferred_name(phone, briefing_name, db)
                await db.commit()
        except Exception:
            logger.exception("save_lead failed for %s", phone)
        try:
            await notify_luciana(briefing, phone)
        except Exception:
            logger.exception("notify_luciana failed for %s", phone)

    await asyncio.gather(send_task, audit_task, return_exceptions=True)

    # Reagenda lembretes de inatividade a partir do momento atual.
    # cancel + reschedule é idempotente (vide app/reminders.py).
    await schedule_reminders(phone)


async def _persist_conversation(
    phone: str,
    user_text: str,
    reply: str,
    model_used: str,
) -> None:
    """Grava as duas mensagens (user + assistant) na tabela conversations."""
    try:
        async with SessionLocal() as db:
            db.add_all(
                [
                    Conversation(phone=phone, role="user", content=user_text),
                    Conversation(
                        phone=phone,
                        role="assistant",
                        content=reply,
                        model_used=model_used,
                    ),
                ]
            )
            await db.commit()
    except Exception:
        logger.exception("persist_conversation failed for %s", phone)

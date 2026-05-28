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
from fastapi.responses import JSONResponse, PlainTextResponse

from app import __version__
from app.ai import route_and_ask
from app.briefing import extract_briefing, notify_luciana, parse_lead_temp, save_lead
from app.config import settings
from app.database import SessionLocal, dispose_engine
from app.models import Conversation
from app.session import close_redis, get_history, get_redis, save_history
from app.whatsapp import parse_incoming, send_message

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
    """Executa o fluxo completo descrito no CLAUDE.md."""
    parsed = parse_incoming(data)
    if parsed is None:
        return
    phone, user_text = parsed

    logger.info("incoming from %s: %s", phone, user_text[:120])

    # 1) Histórico
    history = await get_history(phone)
    history.append({"role": "user", "content": user_text})

    # 2) IA
    reply, model_used = await route_and_ask(history)
    history.append({"role": "assistant", "content": reply})

    # 3) Persiste histórico Redis (best effort)
    await save_history(phone, history)

    # 4) Log de auditoria + envio WhatsApp + briefing — em paralelo onde possível
    send_task = asyncio.create_task(send_message(phone, reply))
    audit_task = asyncio.create_task(_persist_conversation(phone, user_text, reply, model_used))

    briefing = extract_briefing(reply)
    if briefing:
        temp = parse_lead_temp(briefing)
        try:
            async with SessionLocal() as db:
                await save_lead(phone, briefing, temp, db)
                await db.commit()
        except Exception:
            logger.exception("save_lead failed for %s", phone)
        try:
            await notify_luciana(briefing, phone)
        except Exception:
            logger.exception("notify_luciana failed for %s", phone)

    await asyncio.gather(send_task, audit_task, return_exceptions=True)


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

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
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from app import __version__
from app.ai import extract_lead_data, route_and_ask
from app.api import api_router
from app.api import tick as tick_api
from app.briefing import (
    ask_missing_fields,
    extract_customer_name,
    gate_missing_fields,
    lead_columns_from_data,
    normalize_lead_data,
    notify_luciana,
    notify_luciana_ai_down,
    notify_luciana_media,
    notify_luciana_returning_client,
    parse_lead_temp,
    render_briefing,
    save_lead,
    split_reply_and_briefing,
    split_reply_and_transfer,
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
from app.debounce import collect_burst
from app.models import Conversation
from app.push import send_push_to_all
from app.reminders import cancel_reminders, schedule_callbacks
from app.reservas import has_reserva_ativa
from app.sanitize import price_guard, sanitize_outgoing
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
from app.audioconv import transcode_to_mp3
from app.storage import upload_audio
from app.transcribe import transcribe_audio
from app.whatsapp import (
    MEDIA_HANDOFF_REPLY,
    detect_audio_message,
    detect_non_text_message,
    download_media,
    parse_incoming,
    send_message,
)

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("malu")

# Fechamento pro cliente quando a coleta termina (o briefing detalhado vai só
# pra Lu). Inclui o convite pro Instagram e pro grupo VIP de promoções — muitos
# clientes fecham vendo as promos do grupo. (Para multi-tenant, virar config
# por agência.)
COLETA_CONCLUIDA_REPLY = (
    "Recebi tudo! Já vou organizar pra Lu preparar sua cotação com calma. ✈️\n\n"
    "Enquanto isso, segue a gente e entra no nosso grupo de promoções — é onde "
    "saem as melhores oportunidades, sem spam:\n\n"
    "Instagram: https://instagram.com/lumilhaseviagens\n"
    "Grupo VIP: https://chat.whatsapp.com/KkWYCAtn3z46bg8W0rK4oc\n\n"
    "Logo a Lu te chama por aqui. 🙂"
)

# Mensagem ÚNICA quando a IA cai (primária + reserva). A Malu avisa o cliente
# uma vez, sinaliza que a Lu assume e silencia (não repete o erro a cada turno).
IA_FALHA_REPLY = (
    "Opa, tive um probleminha técnico aqui agora 😅\n\n"
    "Já avisei a Lu e ela vai continuar seu atendimento pessoalmente por aqui, "
    "tá? Já já ela te responde. 💛"
)


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

# Endpoint do cron (/internal/tick) — dispara follow-ups + resumo diário.
# Protegido por X-Cron-Secret (CRON_SECRET), fora do /api do painel.
app.include_router(tick_api.router)


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
    # 0) Áudio (nota de voz / arquivo) → transcreve e segue como texto (quando
    #    ligado); desligado ou em erro, cai no handoff de mídia (acolhe + Lu).
    audio = detect_audio_message(data)
    if audio is not None:
        a_phone, a_profile, a_media_id = audio
        logger.info("audio message from %s (profile=%r)", a_phone, a_profile)
        # Já transferida? Malu fica em silêncio (Lu cuida) — só audita.
        if await get_state(a_phone) == STATE_TRANSFERRED:
            asyncio.create_task(
                _persist_conversation(a_phone, "[áudio]", "", "transferred")
            )
            return
        await _handle_audio_message(a_phone, a_profile, a_media_id)
        return

    # 0b) Outras mídias (imagem/vídeo/documento) → handoff pra Lu (como hoje).
    #     A Malu NÃO lê/extrai — acolhe e passa pra Lu.
    non_text = detect_non_text_message(data)
    if non_text is not None:
        nt_phone, nt_profile, nt_type = non_text
        logger.info(
            "non-text message type=%s from %s (profile=%r)",
            nt_type, nt_phone, nt_profile,
        )
        # Já transferida? Malu fica em silêncio (Lu cuida) — só audita.
        if await get_state(nt_phone) == STATE_TRANSFERRED:
            asyncio.create_task(
                _persist_conversation(nt_phone, f"[mídia: {nt_type}]", "", "transferred")
            )
            return
        await _handle_media_message(nt_phone, nt_profile, nt_type)
        return

    parsed = parse_incoming(data)
    if parsed is None:
        return
    phone, user_text, profile_name = parsed
    await _process_text_message(phone, user_text, profile_name)


async def _process_text_message(
    phone: str,
    user_text: str,
    profile_name: str | None,
    from_audio: bool = False,
    media_path: str | None = None,
) -> None:
    """Processa uma mensagem de TEXTO (ou um áudio já transcrito).

    Mesmo fluxo de decisão de `handle_message` a partir do passo 1 (/sair →
    transferido → cliente → intent → IA → briefing). `from_audio=True` quando o
    texto veio de um áudio transcrito: pede pra Malu confirmar de leve o que
    entendeu (a transcrição pode ter erros) e pula o debounce (o áudio já é uma
    fala completa). `media_path` = caminho do áudio no Storage (pra Lu ouvir no
    painel), gravado na mensagem do cliente.
    """
    logger.info(
        "incoming from %s (profile=%r)%s: %s",
        phone,
        profile_name,
        " [áudio]" if from_audio else "",
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
    # Debounce (Fase 1C): se o cliente está mandando mensagens picadas em
    # rajada, espera juntá-las e responde uma vez só — evita estourar o limite
    # do Groq e a Malu ficar repetitiva. Quem não é o último da rajada desiste.
    # Áudio pula o debounce: a transcrição já é uma fala completa.
    if not from_audio:
        burst = await collect_burst(phone, user_text)
        if burst is None:
            return
        user_text = "\n".join(burst)
        history = await get_history(phone)  # relê após a espera (estado mais fresco)

    history.append({"role": "user", "content": user_text})
    customer_context = {
        "name": customer_name,
        "is_first_turn": is_first_turn,
        "from_audio": from_audio,
    }
    reply, model_used = await route_and_ask(history, customer_context=customer_context)

    # As DUAS IAs falharam (primária + reserva). Em vez de repetir o erro a cada
    # mensagem (parecendo quebrada), a Malu avisa UMA vez, silencia e chama a Lu.
    if model_used == "error":
        await _handle_ai_failure(phone, user_text, customer_name)
        return

    # O bloco "## Resumo" é sinal INTERNO de fim de coleta — não vai pro cliente.
    customer_reply, briefing_block = split_reply_and_briefing(reply)
    # "## TRANSFERIR" é sinal INTERNO: cliente quer falar de uma cotação/reserva
    # que a Lu JÁ fez → passa a conversa pra Lu (sem coleta, sem pedir dados).
    customer_reply, wants_transfer = split_reply_and_transfer(customer_reply)

    # Guard de preço (P0) — rede de segurança determinística: se o modelo
    # escapou e citou valor, troca pela frase segura ANTES de qualquer envio.
    # Vale pra todos os modelos da cadeia (o 8b/gemini ignoram regras sutis).
    customer_reply, price_blocked = price_guard(customer_reply)
    if price_blocked:
        logger.warning(
            "price_guard bloqueou valor na resposta ao cliente %s (modelo=%s)",
            phone,
            model_used,
        )

    # Sanitizer de formatação (P2) — converte ** → *, tira # e asterisco órfão
    # antes de enviar (o WhatsApp usa * único pra negrito).
    customer_reply = sanitize_outgoing(customer_reply)

    if wants_transfer:
        await _transfer_to_lu(phone, user_text, customer_reply, customer_name)
        return

    # Coleta concluída (modelo emitiu "## Resumo") → ANTES de fechar, passa pelo
    # GATE de completude: não fecha lead com data vaga, sem passageiros ou sem
    # ter perguntado a indicação (mínimo crítico). Extrai/normaliza 1× e reusa.
    if briefing_block:
        raw = await extract_lead_data(history)
        lead_data = normalize_lead_data(raw) if raw else None
        missing = (
            gate_missing_fields(lead_data, history) if lead_data is not None else []
        )
        if missing:
            # Coleta furada → NÃO finaliza; pede o que falta e segue coletando.
            # (briefing_block=None reaproveita o caminho normal: salva no
            # histórico, agenda lembrete, e o gate re-checa no próximo turno.)
            logger.info("gate barrou finalização p/ %s — faltam: %s", phone, missing)
            customer_reply = ask_missing_fields(missing)
            briefing_block = None
        else:
            numero = await _finalize_lead(phone, history, briefing_block, lead_data)
            # Push web pra Lu (Fase 3) — fire-and-forget, não atrasa a resposta
            # nem quebra o fluxo se o push estiver desligado/falhar.
            titulo = f"Novo lead #{numero}" if numero is not None else "Novo lead"
            asyncio.create_task(
                send_push_to_all(
                    titulo,
                    f"{customer_name or 'Cliente'} — toque pra abrir a conversa",
                    url=f"/conversas/{phone}",
                )
            )
            # Fechamento controlado SEMPRE — CTA (Instagram + grupo VIP) em toda
            # finalização de cotação, não só quando o modelo não escreve nada.
            customer_reply = _build_closing_reply(numero)

            # Coleta concluída → Malu se CALA e o lead fica aguardando a Lu cotar.
            # Sem isso, cada "ok/obrigado" do cliente faz o modelo re-emitir o
            # briefing → lead + protocolo DUPLICADOS a cada mensagem (bug grave).
            await set_state(phone, STATE_TRANSFERRED)
            await cancel_reminders(phone)

    history.append({"role": "assistant", "content": customer_reply})
    await save_history(phone, history)

    # Marca no registro que a entrada veio de áudio transcrito (Lu vê no painel
    # que foi nota de voz — útil se a transcrição tiver errado algo).
    incoming_label = f"🎤 {user_text}" if from_audio else user_text
    send_task = asyncio.create_task(send_message(phone, customer_reply))
    audit_task = asyncio.create_task(
        _persist_conversation(
            phone, incoming_label, customer_reply, model_used, user_media_path=media_path
        )
    )

    await asyncio.gather(send_task, audit_task, return_exceptions=True)

    # Lembrete de inatividade: só enquanto a coleta está em aberto. Se o
    # briefing já foi finalizado (cotação completa), não cutuca — limpa
    # qualquer lembrete pendente. cancel/schedule são idempotentes.
    if briefing_block:
        await cancel_reminders(phone)
    else:
        # t0 = agora (≈ esta mensagem do cliente); agenda 30 min + pré-24h.
        await schedule_callbacks(phone, name=customer_name)


async def _transfer_to_lu(
    phone: str,
    user_text: str,
    customer_reply: str,
    customer_name: str | None,
) -> None:
    """Transfere a conversa pra Lu (cliente quer falar de algo que ela já fez).

    Marca STATE_TRANSFERRED (Malu cala), avisa a Lu e para os lembretes.
    Identifica o cliente pelo telefone — nunca pede código de cotação.
    """
    reply_text = customer_reply or transferred_reply(customer_name)
    await set_state(phone, STATE_TRANSFERRED)
    await cancel_reminders(phone)
    send_task = asyncio.create_task(send_message(phone, reply_text))
    audit_task = asyncio.create_task(
        _persist_conversation(phone, user_text, reply_text, "flow:transfer-marker")
    )
    try:
        await notify_luciana_returning_client(phone, customer_name)
    except Exception:
        logger.exception("notify_luciana_returning_client failed for %s", phone)
    await asyncio.gather(send_task, audit_task, return_exceptions=True)


async def _handle_ai_failure(
    phone: str,
    user_text: str,
    customer_name: str | None,
) -> None:
    """As duas IAs caíram — anti-repetição + chama a Lu.

    Manda UMA mensagem pro cliente, marca STATE_TRANSFERRED (Malu silencia nas
    próximas — nada de repetir o erro), para os lembretes e avisa a Lu pra
    assumir no painel. Quando a Lu "devolver", a Malu volta ao normal.
    """
    logger.warning("IA indisponível (primária+reserva) para %s — chamando a Lu", phone)
    await set_state(phone, STATE_TRANSFERRED)
    await cancel_reminders(phone)
    send_task = asyncio.create_task(send_message(phone, IA_FALHA_REPLY))
    audit_task = asyncio.create_task(
        _persist_conversation(phone, user_text, IA_FALHA_REPLY, "flow:ai-failure")
    )
    try:
        await notify_luciana_ai_down(phone, customer_name)
    except Exception:
        logger.exception("notify_luciana_ai_down failed for %s", phone)
    await asyncio.gather(send_task, audit_task, return_exceptions=True)


async def _handle_audio_message(
    phone: str,
    profile_name: str | None,
    media_id: str,
) -> None:
    """Cliente mandou áudio — transcreve e segue a conversa como texto.

    Se a transcrição estiver desligada, ou falhar (download/Whisper/áudio
    vazio), cai no handoff de mídia de hoje (acolhe + passa pra Lu) — o cliente
    nunca fica sem resposta. Sucesso → entra no fluxo de texto com `from_audio`
    (a Malu confirma de leve o que entendeu).
    """
    if not settings.audio_transcription_enabled:
        await _handle_media_message(phone, profile_name, "audio")
        return

    transcript: str | None = None
    media_path: str | None = None
    try:
        audio_bytes, mime_type = await download_media(media_id)
        # Guarda o áudio pra Lu ouvir no painel (best-effort: se o Storage não
        # estiver configurado ou falhar, volta None e a transcrição segue).
        # Recodifica pra MP3 antes (conserta a duração quebrada do OGG do
        # WhatsApp, que faz o player parar cedo). Se o ffmpeg falhar, sobe o OGG.
        mp3 = await transcode_to_mp3(audio_bytes)
        if mp3:
            media_path = await upload_audio(phone, mp3, "audio/mpeg")
        else:
            media_path = await upload_audio(phone, audio_bytes, mime_type)
        # Transcrição usa o ÁUDIO ORIGINAL (o Whisper lê OGG sem problema).
        transcript = await transcribe_audio(audio_bytes, mime_type)
    except Exception:
        logger.exception("transcrição de áudio falhou para %s", phone)

    if not transcript or not transcript.strip():
        logger.info("áudio de %s sem transcrição utilizável — handoff pra Lu", phone)
        await _handle_media_message(phone, profile_name, "audio", media_path=media_path)
        return

    await _process_text_message(
        phone, transcript.strip(), profile_name, from_audio=True, media_path=media_path
    )


async def _handle_media_message(
    phone: str,
    profile_name: str | None,
    media_type: str,
    media_path: str | None = None,
) -> None:
    """Cliente mandou mídia/documento — a Malu não lê: acolhe e passa pra Lu.

    Marca STATE_TRANSFERRED (Malu cala), para os callbacks, avisa a Lu e
    nunca tenta transcrever/extrair o conteúdo.
    """
    customer_name = profile_name
    try:
        async with SessionLocal() as db:
            cliente = await get_or_create_cliente(phone, profile_name, db)
            await db.commit()
            customer_name = cliente.display_name
    except Exception:
        logger.exception("get_or_create_cliente (media) failed for %s", phone)

    await set_state(phone, STATE_TRANSFERRED)
    await cancel_reminders(phone)
    send_task = asyncio.create_task(send_message(phone, MEDIA_HANDOFF_REPLY))
    audit_task = asyncio.create_task(
        _persist_conversation(
            phone,
            f"[mídia: {media_type}]",
            MEDIA_HANDOFF_REPLY,
            f"media:{media_type}",
            user_media_path=media_path,
        )
    )
    try:
        await notify_luciana_media(phone, customer_name, media_type)
    except Exception:
        logger.exception("notify_luciana_media failed for %s", phone)
    await asyncio.gather(send_task, audit_task, return_exceptions=True)


def _build_closing_reply(numero: int | None) -> str:
    """Mensagem de fechamento ao cliente em toda finalização de cotação.

    O CTA (Instagram + grupo VIP) vai SEMPRE — antes só ia quando o modelo não
    escrevia nada junto do briefing. Mensagem controlada e única por cotação
    (boa pra qualidade Meta). Anexa o protocolo (#1001...) quando houver.
    """
    reply = COLETA_CONCLUIDA_REPLY
    if numero is not None:
        reply = reply.rstrip() + f"\n\n🔖 *Protocolo da sua solicitação:* #{numero}"
    return reply


async def _finalize_lead(
    phone: str,
    history: list[dict[str, Any]],
    briefing_block: str,
    data: dict[str, Any] | None,
) -> int | None:
    """Fecha a coleta: salva o lead (extração já validada pelo gate) e notifica.

    `data` = extração ESTRUTURADA já normalizada (vinda do dispatch, que passou
    pelo gate de completude). Se for None, a IA caiu na extração → cai pro parser
    regex sobre o bloco que a Malu escreveu, rede de segurança pra nunca perder
    um lead.

    Retorna o número de protocolo do lead (#1001...) pra entrar no fechamento,
    ou None se o save falhar.
    """
    if data:
        briefing_md = render_briefing(data, phone)
        cols = lead_columns_from_data(data)
        numero: int | None = None
        try:
            async with SessionLocal() as db:
                lead = await save_lead(
                    phone,
                    db,
                    briefing_md=briefing_md,
                    lead_temp=cols["lead_temp"],
                    name=cols["name"],
                    destination=cols["destination"],
                    travel_type=cols["travel_type"],
                    indicado_por=cols["indicado_por"],
                    raw_data=data,
                )
                numero = lead.numero
                if cols["name"]:
                    await update_preferred_name(phone, cols["name"], db)
                await db.commit()
        except Exception:
            logger.exception("save_lead (estruturado) failed for %s", phone)
        try:
            await notify_luciana(briefing_md, phone, numero=numero)
        except Exception:
            logger.exception("notify_luciana failed for %s", phone)
        return numero

    # Fallback: extração falhou (IA fora) → usa o bloco da Malu via regex
    logger.warning("extração estruturada falhou p/ %s — usando fallback regex", phone)
    temp = parse_lead_temp(briefing_block)
    name = extract_customer_name(briefing_block)
    numero = None
    try:
        async with SessionLocal() as db:
            lead = await save_lead(
                phone,
                db,
                briefing_md=briefing_block,
                lead_temp=temp,
                name=name,
            )
            numero = lead.numero
            if name:
                await update_preferred_name(phone, name, db)
            await db.commit()
    except Exception:
        logger.exception("save_lead (fallback) failed for %s", phone)
    try:
        await notify_luciana(briefing_block, phone, numero=numero)
    except Exception:
        logger.exception("notify_luciana (fallback) failed for %s", phone)
    return numero


async def _persist_conversation(
    phone: str,
    user_text: str,
    reply: str,
    model_used: str,
    user_media_path: str | None = None,
) -> None:
    """Grava as duas mensagens (user + assistant) na tabela conversations.

    Timestamps DISTINTOS (Malu 10ms depois do cliente) garantem a ordem no
    painel — senão as duas empatam no mesmo instante e a thread embaralha
    (resposta da Malu aparecendo antes da pergunta do cliente).

    `user_media_path` = caminho do áudio do cliente no Storage (só quando a
    mensagem veio de uma nota de voz), gravado na linha do cliente.
    """
    try:
        async with SessionLocal() as db:
            now = datetime.now(timezone.utc)
            db.add_all(
                [
                    Conversation(
                        phone=phone,
                        role="user",
                        content=user_text,
                        media_path=user_media_path,
                        created_at=now,
                    ),
                    Conversation(
                        phone=phone,
                        role="assistant",
                        content=reply,
                        model_used=model_used,
                        created_at=now + timedelta(milliseconds=10),
                    ),
                ]
            )
            await db.commit()
    except Exception:
        logger.exception("persist_conversation failed for %s", phone)

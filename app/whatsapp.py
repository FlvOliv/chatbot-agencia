"""Cliente Meta WhatsApp Cloud API — envio e parse de mensagens.

Documentação: https://developers.facebook.com/docs/whatsapp/cloud-api
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v21.0"
# O envio de áudio (nota de voz) usa a flag `voice: true`, que só existe em
# versões mais novas da Graph. Isolado aqui pra NÃO mexer no caminho de texto
# (v21.0, estável). Cloud API é retrocompatível.
AUDIO_GRAPH_API_VERSION = "v23.0"


def _api_url() -> str:
    return f"https://graph.facebook.com/{GRAPH_API_VERSION}/{settings.wa_phone_id}/messages"


def _audio_messages_url() -> str:
    return f"https://graph.facebook.com/{AUDIO_GRAPH_API_VERSION}/{settings.wa_phone_id}/messages"


def _media_upload_url() -> str:
    return f"https://graph.facebook.com/{AUDIO_GRAPH_API_VERSION}/{settings.wa_phone_id}/media"


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.wa_token}",
        "Content-Type": "application/json",
    }


async def send_message(to: str, text: str) -> bool:
    """Envia mensagem de texto pelo Meta Cloud API.

    Args:
        to: telefone do destinatário (E.164 sem '+')
        text: corpo da mensagem (até 4096 chars)

    Returns:
        True se 2xx, False caso contrário.
    """
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": text},
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(_api_url(), headers=_headers(), json=payload)
        if resp.status_code >= 400:
            logger.error(
                "whatsapp send_message failed status=%s body=%s",
                resp.status_code,
                resp.text,
            )
            return False
        # Loga o message_id e o destinatário pra rastrear entrega
        try:
            data = resp.json()
            msgs = data.get("messages", [])
            if msgs:
                msg_id = msgs[0].get("id", "?")
                contacts = data.get("contacts", [])
                wa_id = contacts[0].get("wa_id") if contacts else "?"
                logger.info(
                    "whatsapp send_message OK to=%s wa_id=%s message_id=%s",
                    to, wa_id, msg_id,
                )
            else:
                logger.warning(
                    "whatsapp send_message accepted but no message id: %s",
                    resp.text[:300],
                )
        except Exception:  # noqa: BLE001
            logger.debug("could not parse Meta send response: %s", resp.text[:300])
        return True
    except httpx.HTTPError:
        logger.exception("whatsapp send_message HTTP error for %s", to)
        return False


async def upload_media(
    audio_bytes: bytes,
    mime_type: str = "audio/ogg",
    filename: str = "nota.ogg",
) -> str | None:
    """Sobe mídia pra Graph API (passo 1 do envio) e devolve o `media_id`.

    Multipart: `file` (binário) + `messaging_product=whatsapp` + `type` (MIME).
    Retorna `None` em falha (logada) — o chamador decide o que fazer.
    """
    if not audio_bytes:
        return None

    auth = {"Authorization": f"Bearer {settings.wa_token}"}
    data = {"messaging_product": "whatsapp", "type": mime_type}
    files = {"file": (filename, audio_bytes, mime_type)}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                _media_upload_url(), headers=auth, data=data, files=files
            )
        if resp.status_code >= 400:
            logger.error(
                "whatsapp upload_media failed status=%s body=%s",
                resp.status_code,
                resp.text,
            )
            return None
        return (resp.json() or {}).get("id")
    except httpx.HTTPError:
        logger.exception("whatsapp upload_media HTTP error")
        return None


async def send_audio(to: str, media_id: str, voice: bool = True) -> bool:
    """Envia áudio pelo Cloud API (passo 2). Com `voice=True` vira nota de voz.

    Defensivo: se a Meta recusar a flag `voice` (versão/compat), reenvia UMA vez
    sem ela — vira anexo de áudio comum, mas ainda toca pro cliente.
    """

    def _payload(with_voice: bool) -> dict[str, Any]:
        audio: dict[str, Any] = {"id": media_id}
        if with_voice:
            audio["voice"] = True
        return {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "audio",
            "audio": audio,
        }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                _audio_messages_url(), headers=_headers(), json=_payload(voice)
            )
            if resp.status_code >= 400 and voice:
                logger.warning(
                    "send_audio voice=true recusado (status=%s) — retry sem voice. body=%s",
                    resp.status_code,
                    resp.text[:300],
                )
                resp = await client.post(
                    _audio_messages_url(), headers=_headers(), json=_payload(False)
                )
            if resp.status_code >= 400:
                logger.error(
                    "whatsapp send_audio failed status=%s body=%s",
                    resp.status_code,
                    resp.text,
                )
                return False
        logger.info("whatsapp send_audio OK to=%s media_id=%s", to, media_id)
        return True
    except httpx.HTTPError:
        logger.exception("whatsapp send_audio HTTP error for %s", to)
        return False


async def send_template(to: str, template: str, params: list[str]) -> bool:
    """Envia mensagem usando um template pré-aprovado.

    Args:
        to: telefone destinatário (E.164 sem '+')
        template: nome do template aprovado na Meta
        params: parâmetros posicionais do body do template
    """
    payload: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": template,
            "language": {"code": "pt_BR"},
            "components": [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": p} for p in params],
                }
            ],
        },
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(_api_url(), headers=_headers(), json=payload)
        if resp.status_code >= 400:
            logger.error(
                "whatsapp send_template failed status=%s body=%s",
                resp.status_code,
                resp.text,
            )
            return False
        return True
    except httpx.HTTPError:
        logger.exception("whatsapp send_template HTTP error for %s", to)
        return False


# Tipos de áudio (nota de voz e arquivo de áudio). Tratados ANTES do handoff
# genérico: se a transcrição estiver ligada, a Malu transcreve e segue a
# conversa; senão (ou em erro), cai no handoff de mídia abaixo.
AUDIO_MESSAGE_TYPES: frozenset[str] = frozenset({"audio", "voice"})

# Tipos de mensagem WhatsApp que NÃO são texto — a Malu não consome ainda,
# mas reconhece e responde educadamente em vez de ficar muda.
# Lista oficial: https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/payload-examples
NON_TEXT_MESSAGE_TYPES: frozenset[str] = frozenset(
    {
        "audio",
        "image",
        "video",
        "document",
        "sticker",
        "voice",
        "location",
        "contacts",
    }
)

# Resposta quando o cliente manda mídia/documento: a Malu não lê — acolhe e
# passa pra Lu (sem prometer transcrição/leitura). Tom acolhedor, ≤1 emoji.
MEDIA_HANDOFF_REPLY: str = (
    "Oi! Recebi seu arquivo aqui 🙌\n\n"
    "Pra cuidar disso com a atenção que merece, já estou chamando a Lu — "
    "ela continua seu atendimento por aqui. Já já ela te responde!"
)


def _extract_phone_and_profile(
    value: dict[str, Any],
    msg: dict[str, Any],
) -> tuple[str | None, str | None]:
    """Helper interno — extrai phone e profile_name de um payload Meta."""
    phone = msg.get("from")
    contacts = value.get("contacts", []) or []
    profile_name: str | None = None
    if contacts:
        profile = contacts[0].get("profile") or {}
        raw = profile.get("name")
        if isinstance(raw, str) and raw.strip():
            profile_name = raw.strip()
    return phone, profile_name


def parse_incoming(
    data: dict[str, Any],
) -> tuple[str, str, str | None] | None:
    """Extrai `(phone, text, profile_name)` do payload do webhook.

    `profile_name` é o nome do perfil WhatsApp do cliente (vem de
    `contacts[0].profile.name`). Pode ser `None` se o cliente não tem nome
    configurado ou se a Meta não enviou.

    Retorna `None` para qualquer payload que não seja mensagem de texto
    (status updates, reações, áudio, mídia, etc.).

    Para detectar tipos não-texto e responder educadamente, use
    `detect_non_text_message()`.
    """
    try:
        entry = data.get("entry", [])
        if not entry:
            return None
        changes = entry[0].get("changes", [])
        if not changes:
            return None
        value = changes[0].get("value", {})
        messages = value.get("messages", [])
        if not messages:
            return None

        msg = messages[0]
        if msg.get("type") != "text":
            return None

        text = msg.get("text", {}).get("body")
        phone, profile_name = _extract_phone_and_profile(value, msg)
        if not phone or not text:
            return None
        return phone, text, profile_name
    except (KeyError, IndexError, AttributeError, TypeError):
        logger.exception("parse_incoming failed")
        return None


def detect_non_text_message(
    data: dict[str, Any],
) -> tuple[str, str | None, str] | None:
    """Detecta mensagem do tipo áudio/imagem/vídeo/sticker/etc.

    Retorna `(phone, profile_name, msg_type)` se for uma mensagem de mídia
    suportada para resposta educada. Retorna `None` se for texto, payload
    inválido, ou tipo que devemos simplesmente ignorar (status updates).
    """
    try:
        entry = data.get("entry", [])
        if not entry:
            return None
        changes = entry[0].get("changes", [])
        if not changes:
            return None
        value = changes[0].get("value", {})
        messages = value.get("messages", [])
        if not messages:
            return None

        msg = messages[0]
        msg_type = msg.get("type")
        if msg_type not in NON_TEXT_MESSAGE_TYPES:
            return None

        phone, profile_name = _extract_phone_and_profile(value, msg)
        if not phone:
            return None
        return phone, profile_name, msg_type
    except (KeyError, IndexError, AttributeError, TypeError):
        logger.exception("detect_non_text_message failed")
        return None


def detect_audio_message(
    data: dict[str, Any],
) -> tuple[str, str | None, str] | None:
    """Detecta mensagem de áudio/voz e devolve `(phone, profile_name, media_id)`.

    O `media_id` é o id da mídia na Graph API — usado por `download_media()`
    pra baixar os bytes do áudio. Retorna `None` se não for áudio, payload
    inválido, ou se faltar telefone/id.
    """
    try:
        entry = data.get("entry", [])
        if not entry:
            return None
        changes = entry[0].get("changes", [])
        if not changes:
            return None
        value = changes[0].get("value", {})
        messages = value.get("messages", [])
        if not messages:
            return None

        msg = messages[0]
        msg_type = msg.get("type")
        if msg_type not in AUDIO_MESSAGE_TYPES:
            return None

        media = msg.get(msg_type) or {}
        media_id = media.get("id")
        phone, profile_name = _extract_phone_and_profile(value, msg)
        if not phone or not media_id:
            return None
        return phone, profile_name, media_id
    except (KeyError, IndexError, AttributeError, TypeError):
        logger.exception("detect_audio_message failed")
        return None


async def download_media(media_id: str) -> tuple[bytes, str]:
    """Baixa os bytes de uma mídia do WhatsApp (2 passos da Graph API).

    1) `GET /{media_id}` → metadados (URL temporária + `mime_type`)
    2) `GET <url>` → bytes binários (precisa do MESMO Bearer token)

    Retorna `(bytes, mime_type)`. Lança em erro de rede/HTTP ou se a mídia
    não tiver URL de download.
    """
    meta_url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{media_id}"
    auth = {"Authorization": f"Bearer {settings.wa_token}"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        meta_resp = await client.get(meta_url, headers=auth)
        meta_resp.raise_for_status()
        meta = meta_resp.json()
        media_url = meta.get("url")
        mime_type = meta.get("mime_type") or "audio/ogg"
        if not media_url:
            raise RuntimeError(f"mídia {media_id} sem URL de download")
        bin_resp = await client.get(media_url, headers=auth)
        bin_resp.raise_for_status()
        return bin_resp.content, mime_type

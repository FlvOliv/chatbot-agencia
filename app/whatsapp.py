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


def _api_url() -> str:
    return f"https://graph.facebook.com/{GRAPH_API_VERSION}/{settings.wa_phone_id}/messages"


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

# Resposta padrão quando o cliente manda algo que não é texto.
# Mantém o tom acolhedor da Malu sem prometer suporte futuro.
NON_TEXT_REPLY: str = (
    "Oi! Por enquanto eu só consigo entender mensagens de texto. 😊\n\n"
    "Pode escrever o que você precisa? Assim a Lu consegue te atender com mais rapidez."
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

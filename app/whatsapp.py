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


def parse_incoming(
    data: dict[str, Any],
) -> tuple[str, str, str | None] | None:
    """Extrai `(phone, text, profile_name)` do payload do webhook.

    `profile_name` é o nome do perfil WhatsApp do cliente (vem de
    `contacts[0].profile.name`). Pode ser `None` se o cliente não tem nome
    configurado ou se a Meta não enviou.

    Retorna `None` para qualquer payload que não seja mensagem de texto
    (status updates, reações, áudio, mídia, etc.).
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

        phone = msg.get("from")
        text = msg.get("text", {}).get("body")
        if not phone or not text:
            return None

        # profile_name vem de contacts[0].profile.name (pode estar ausente)
        contacts = value.get("contacts", []) or []
        profile_name: str | None = None
        if contacts:
            profile = contacts[0].get("profile") or {}
            raw = profile.get("name")
            if isinstance(raw, str) and raw.strip():
                profile_name = raw.strip()

        return phone, text, profile_name
    except (KeyError, IndexError, AttributeError, TypeError):
        logger.exception("parse_incoming failed")
        return None

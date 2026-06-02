"""Testes da detecção de mensagens não-texto (áudio/imagem/vídeo/etc)."""

from __future__ import annotations

import pytest

from app.whatsapp import (
    NON_TEXT_MESSAGE_TYPES,
    NON_TEXT_REPLY,
    detect_non_text_message,
    parse_incoming,
)


def _make_payload(msg_type: str, with_profile: bool = True) -> dict:
    """Monta um payload-modelo da Meta com o `type` indicado."""
    msg: dict = {"from": "5511999998888", "type": msg_type}
    # Cada tipo tem sub-objeto próprio — só preenche se relevante (não usamos no parser)
    if msg_type == "text":
        msg["text"] = {"body": "oi"}
    elif msg_type == "audio":
        msg["audio"] = {"id": "media_id_123", "mime_type": "audio/ogg"}
    elif msg_type == "image":
        msg["image"] = {"id": "media_id_456", "mime_type": "image/jpeg"}
    elif msg_type == "video":
        msg["video"] = {"id": "media_id_789", "mime_type": "video/mp4"}

    contacts = []
    if with_profile:
        contacts.append({"profile": {"name": "Cliente Teste"}, "wa_id": "5511999998888"})

    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [msg],
                            "contacts": contacts,
                        }
                    }
                ]
            }
        ]
    }


# ---------------------------------------------------------------------------
# detect_non_text_message — caminhos positivos
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "msg_type",
    sorted(NON_TEXT_MESSAGE_TYPES),
)
def test_detects_all_supported_non_text_types(msg_type: str) -> None:
    payload = _make_payload(msg_type)
    result = detect_non_text_message(payload)
    assert result is not None, f"falhou em detectar tipo {msg_type!r}"
    phone, profile_name, detected_type = result
    assert phone == "5511999998888"
    assert profile_name == "Cliente Teste"
    assert detected_type == msg_type


def test_detects_audio_without_profile_name() -> None:
    payload = _make_payload("audio", with_profile=False)
    result = detect_non_text_message(payload)
    assert result is not None
    phone, profile_name, msg_type = result
    assert phone == "5511999998888"
    assert profile_name is None
    assert msg_type == "audio"


# ---------------------------------------------------------------------------
# detect_non_text_message — caminhos negativos
# ---------------------------------------------------------------------------
def test_text_message_returns_none() -> None:
    """Texto não deve ser detectado como non-text."""
    assert detect_non_text_message(_make_payload("text")) is None


def test_unknown_type_returns_none() -> None:
    """Tipos desconhecidos (ex: reactions, system) são ignorados."""
    payload = _make_payload("text")
    payload["entry"][0]["changes"][0]["value"]["messages"][0]["type"] = "reaction"
    assert detect_non_text_message(payload) is None


def test_empty_payload_returns_none() -> None:
    assert detect_non_text_message({}) is None
    assert detect_non_text_message({"entry": []}) is None


def test_status_update_returns_none() -> None:
    """Status updates (delivered/read) não têm `messages` — devem ser ignorados."""
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "statuses": [{"id": "wamid.xxx", "status": "delivered"}],
                        }
                    }
                ]
            }
        ]
    }
    assert detect_non_text_message(payload) is None


# ---------------------------------------------------------------------------
# parse_incoming continua funcionando pra texto (regressão)
# ---------------------------------------------------------------------------
def test_parse_incoming_still_works_for_text() -> None:
    payload = _make_payload("text")
    result = parse_incoming(payload)
    assert result is not None
    phone, text, profile_name = result
    assert phone == "5511999998888"
    assert text == "oi"
    assert profile_name == "Cliente Teste"


def test_parse_incoming_returns_none_for_non_text() -> None:
    """parse_incoming não deve confundir áudio com texto."""
    assert parse_incoming(_make_payload("audio")) is None
    assert parse_incoming(_make_payload("image")) is None


# ---------------------------------------------------------------------------
# NON_TEXT_REPLY — qualidade
# ---------------------------------------------------------------------------
def test_non_text_reply_is_warm_and_useful() -> None:
    assert NON_TEXT_REPLY
    assert len(NON_TEXT_REPLY) > 50
    # Menciona texto explicitamente — orienta o cliente
    assert "texto" in NON_TEXT_REPLY.lower()
    # Não promete suporte futuro ("em breve", "estou aprendendo") — evita expectativa errada
    assert "em breve" not in NON_TEXT_REPLY.lower()
    assert "aprendendo" not in NON_TEXT_REPLY.lower()

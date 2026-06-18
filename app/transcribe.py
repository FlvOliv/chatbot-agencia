"""Transcrição de áudio via Whisper da Groq (endpoint OpenAI-compatible).

A Malu usa a MESMA chave do Groq que já usa pra conversar. A cota de
transcrição (ASR) é SEPARADA da cota de chat — então um 429 nos modelos de
texto (o que dispara a cadeia de fallback) normalmente NÃO afeta o Whisper.

Só transcreve áudio (nota de voz / arquivo de áudio). Se a chamada falhar, o
chamador decide o fallback — no nosso caso, passar a conversa pra Lu.
"""

from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

GROQ_TRANSCRIBE_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


async def transcribe_audio(audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
    """Transcreve bytes de áudio com o Whisper da Groq e retorna o texto.

    Args:
        audio_bytes: conteúdo binário do áudio (ex.: ogg/opus do WhatsApp).
        mime_type: tipo do arquivo (informativo no multipart).

    Returns:
        Texto transcrito (pode ser "" se a API não devolver nada).

    Lança em chave ausente ou erro de rede/HTTP — o chamador trata o fallback.
    """
    if not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY não configurada — sem transcrição")
    if not audio_bytes:
        return ""

    files = {"file": ("audio.ogg", audio_bytes, mime_type)}
    data = {
        "model": settings.groq_whisper_model,
        # pt: o público da Lu fala português; fixar o idioma melhora a precisão.
        "language": "pt",
        "response_format": "json",
        "temperature": "0",
    }
    headers = {"Authorization": f"Bearer {settings.groq_api_key}"}

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            GROQ_TRANSCRIBE_URL, headers=headers, files=files, data=data
        )
        resp.raise_for_status()
        payload = resp.json()

    text = (payload.get("text") or "").strip()
    logger.info(
        "[transcribe] groq/%s chars=%d", settings.groq_whisper_model, len(text)
    )
    return text

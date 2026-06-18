"""Supabase Storage — guarda os áudios dos clientes e gera links assinados.

Bucket PRIVADO + URL assinada temporária (LGPD-friendly): o painel só recebe um
link que expira. Usa a REST API do Storage via httpx (sem SDK novo), com a
`service_role` key (que ignora RLS pra upload).

Robustez: qualquer falha (sem config, rede, HTTP) é logada e vira `None` — NUNCA
quebra o fluxo do chat. Sem áudio guardado, o painel só mostra o texto transcrito.
"""

from __future__ import annotations

import logging
import uuid

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# mime → extensão do arquivo (o WhatsApp manda ogg/opus por padrão).
_EXT_BY_MIME = {
    "audio/ogg": "ogg",
    "audio/opus": "ogg",
    "audio/mpeg": "mp3",
    "audio/mp4": "m4a",
    "audio/aac": "aac",
    "audio/wav": "wav",
    "audio/webm": "webm",
}


def storage_configured() -> bool:
    """True se dá pra falar com o Supabase Storage (URL + chave presentes)."""
    return bool(settings.supabase_url and settings.supabase_service_key)


def _ext_for(mime_type: str) -> str:
    return _EXT_BY_MIME.get((mime_type or "").split(";")[0].strip(), "ogg")


async def upload_audio(
    phone: str, audio_bytes: bytes, mime_type: str = "audio/ogg"
) -> str | None:
    """Sobe o áudio pro bucket e retorna o caminho (dentro do bucket) ou `None`.

    Caminho: `{phone}/{uuid}.{ext}`. Falha/sem config → `None` (não quebra nada).
    """
    if not storage_configured() or not audio_bytes:
        return None

    bucket = settings.supabase_audio_bucket
    path = f"{phone}/{uuid.uuid4().hex}.{_ext_for(mime_type)}"
    url = f"{settings.supabase_url.rstrip('/')}/storage/v1/object/{bucket}/{path}"
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_key}",
        "Content-Type": mime_type or "application/octet-stream",
        "x-upsert": "true",
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, content=audio_bytes)
            resp.raise_for_status()
    except Exception:
        logger.exception("upload_audio falhou para %s (bucket=%s)", phone, bucket)
        return None

    logger.info("[storage] áudio guardado: %s/%s (%d bytes)", bucket, path, len(audio_bytes))
    return path


async def signed_url(path: str | None) -> str | None:
    """Gera um link assinado temporário pro áudio guardado, ou `None`.

    `path` é o que `upload_audio` devolveu. O link expira em `AUDIO_URL_TTL`.
    """
    if not path or not storage_configured():
        return None

    bucket = settings.supabase_audio_bucket
    base = settings.supabase_url.rstrip("/")
    url = f"{base}/storage/v1/object/sign/{bucket}/{path}"
    headers = {"Authorization": f"Bearer {settings.supabase_service_key}"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                url, headers=headers, json={"expiresIn": settings.audio_url_ttl}
            )
            resp.raise_for_status()
            signed = (resp.json() or {}).get("signedURL")
    except Exception:
        logger.exception("signed_url falhou para %s", path)
        return None

    if not signed:
        return None
    # A API devolve um caminho relativo tipo "/object/sign/...". Monta a URL cheia.
    return f"{base}/storage/v1{signed}" if signed.startswith("/") else signed

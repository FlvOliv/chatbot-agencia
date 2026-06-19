"""Conversão de áudio via ffmpeg — conserta as notas de voz do WhatsApp.

As notas de voz vêm em Opus/OGG com a tabela de tempo (granule) quebrada/curta:
no navegador, o `<audio>` lê essa duração errada e PARA a reprodução cedo
(~3s), embora o arquivo tenha o áudio inteiro. Recodificar pra MP3 decodifica
todos os pacotes e regrava com a duração correta → toca inteiro em qualquer
navegador, com barra de progresso funcionando.

Roda o ffmpeg por subprocess (stdin→stdout). Se o ffmpeg não existir (ex.: dev
local sem ffmpeg) ou falhar, retorna `None` e o chamador usa os bytes originais.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


async def transcode_to_mp3(audio_bytes: bytes) -> bytes | None:
    """Recodifica `audio_bytes` (qualquer formato) pra MP3. `None` em falha."""
    if not audio_bytes:
        return None

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-i", "pipe:0",
        "-vn",                      # sem vídeo
        "-acodec", "libmp3lame",
        "-q:a", "5",                # VBR ~130kbps — ótimo p/ voz, arquivo pequeno
        "-f", "mp3",
        "pipe:1",
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate(input=audio_bytes)
        if proc.returncode != 0 or not out:
            logger.warning(
                "ffmpeg falhou (rc=%s): %s",
                proc.returncode, (err or b"")[:200].decode("utf-8", "replace"),
            )
            return None
        logger.info("[audioconv] OGG→MP3 ok (%d→%d bytes)", len(audio_bytes), len(out))
        return out
    except FileNotFoundError:
        logger.warning("ffmpeg não encontrado — usando áudio original (OGG)")
        return None
    except Exception:
        logger.exception("transcode_to_mp3 erro inesperado")
        return None

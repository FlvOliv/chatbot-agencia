"""Testes da conversão de áudio (app/audioconv.py) — ffmpeg mockado."""

from __future__ import annotations

import pytest

from app import audioconv


class _FakeProc:
    def __init__(self, returncode: int, out: bytes, err: bytes = b"") -> None:
        self.returncode = returncode
        self._out = out
        self._err = err

    async def communicate(self, input: bytes | None = None):  # noqa: A002
        return self._out, self._err


@pytest.mark.asyncio
async def test_transcode_empty_returns_none() -> None:
    assert await audioconv.transcode_to_mp3(b"") is None


@pytest.mark.asyncio
async def test_transcode_success_returns_mp3_bytes(monkeypatch) -> None:
    async def fake_exec(*args, **kwargs):  # noqa: ANN002, ANN003
        return _FakeProc(0, b"ID3-mp3-bytes")

    monkeypatch.setattr(audioconv.asyncio, "create_subprocess_exec", fake_exec)
    out = await audioconv.transcode_to_mp3(b"ogg-bytes")
    assert out == b"ID3-mp3-bytes"


@pytest.mark.asyncio
async def test_transcode_ffmpeg_error_returns_none(monkeypatch) -> None:
    async def fake_exec(*args, **kwargs):  # noqa: ANN002, ANN003
        return _FakeProc(1, b"", b"boom")

    monkeypatch.setattr(audioconv.asyncio, "create_subprocess_exec", fake_exec)
    assert await audioconv.transcode_to_mp3(b"ogg-bytes") is None


@pytest.mark.asyncio
async def test_transcode_no_ffmpeg_returns_none(monkeypatch) -> None:
    async def fake_exec(*args, **kwargs):  # noqa: ANN002, ANN003
        raise FileNotFoundError("ffmpeg")

    monkeypatch.setattr(audioconv.asyncio, "create_subprocess_exec", fake_exec)
    assert await audioconv.transcode_to_mp3(b"ogg-bytes") is None

"""Testes da transcrição de áudio (app/transcribe.py) — Whisper da Groq mockado."""

from __future__ import annotations

import pytest

from app import transcribe


class _FakeResp:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    """Cliente httpx falso que captura o POST e devolve uma transcrição fixa."""

    captured: dict = {}

    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        pass

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *args) -> bool:  # noqa: ANN002
        return False

    async def post(self, url, headers=None, files=None, data=None):  # noqa: ANN001
        _FakeClient.captured = {
            "url": url,
            "headers": headers,
            "files": files,
            "data": data,
        }
        return _FakeResp({"text": "  quero ir pra Bariloche em julho  "})


@pytest.mark.asyncio
async def test_transcribe_returns_text_and_calls_groq(monkeypatch) -> None:
    monkeypatch.setattr(transcribe.settings, "groq_api_key", "test-groq-key")
    monkeypatch.setattr(transcribe.httpx, "AsyncClient", _FakeClient)

    text = await transcribe.transcribe_audio(b"fake-audio-bytes", "audio/ogg")

    assert text == "quero ir pra Bariloche em julho"  # trim aplicado
    cap = _FakeClient.captured
    assert cap["url"] == transcribe.GROQ_TRANSCRIBE_URL
    assert cap["headers"]["Authorization"] == "Bearer test-groq-key"
    assert cap["data"]["model"] == transcribe.settings.groq_whisper_model
    assert cap["data"]["language"] == "pt"
    assert cap["files"]["file"][1] == b"fake-audio-bytes"


@pytest.mark.asyncio
async def test_transcribe_empty_bytes_returns_empty(monkeypatch) -> None:
    monkeypatch.setattr(transcribe.settings, "groq_api_key", "test-groq-key")
    # Não deve nem tentar chamar a API com áudio vazio.
    monkeypatch.setattr(transcribe.httpx, "AsyncClient", _FakeClient)
    assert await transcribe.transcribe_audio(b"", "audio/ogg") == ""


@pytest.mark.asyncio
async def test_transcribe_without_key_raises(monkeypatch) -> None:
    monkeypatch.setattr(transcribe.settings, "groq_api_key", "")
    with pytest.raises(RuntimeError):
        await transcribe.transcribe_audio(b"fake-audio-bytes", "audio/ogg")

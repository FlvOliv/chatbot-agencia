"""Testes do envio de áudio pela Cloud API (app/whatsapp.py) — httpx mockado."""

from __future__ import annotations

import pytest

from app import whatsapp


class _Resp:
    def __init__(self, status_code: int = 200, payload: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    """Cliente httpx falso: captura os POSTs e devolve respostas de uma fila."""

    posts: list[dict] = []
    responses: list[_Resp] = []

    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        pass

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *args) -> bool:  # noqa: ANN002
        return False

    async def post(self, url, headers=None, json=None, data=None, files=None):  # noqa: ANN001
        _FakeClient.posts.append(
            {"url": url, "json": json, "data": data, "files": files}
        )
        if _FakeClient.responses:
            return _FakeClient.responses.pop(0)
        return _Resp(200, {"id": "MEDIA_DEFAULT"})


@pytest.fixture(autouse=True)
def _setup(monkeypatch) -> None:
    _FakeClient.posts = []
    _FakeClient.responses = []
    monkeypatch.setattr(whatsapp.settings, "wa_token", "test-token")
    monkeypatch.setattr(whatsapp.settings, "wa_phone_id", "PHONE123")
    monkeypatch.setattr(whatsapp.httpx, "AsyncClient", _FakeClient)


@pytest.mark.asyncio
async def test_upload_media_returns_id() -> None:
    _FakeClient.responses = [_Resp(200, {"id": "MEDIA123"})]
    media_id = await whatsapp.upload_media(b"ogg-bytes", "audio/ogg", "nota.ogg")

    assert media_id == "MEDIA123"
    cap = _FakeClient.posts[0]
    assert "/PHONE123/media" in cap["url"]
    assert whatsapp.AUDIO_GRAPH_API_VERSION in cap["url"]
    assert cap["data"] == {"messaging_product": "whatsapp", "type": "audio/ogg"}
    assert cap["files"]["file"][1] == b"ogg-bytes"


@pytest.mark.asyncio
async def test_upload_media_empty_returns_none() -> None:
    assert await whatsapp.upload_media(b"") is None
    assert _FakeClient.posts == []  # nem tenta chamar


@pytest.mark.asyncio
async def test_upload_media_http_error_returns_none() -> None:
    _FakeClient.responses = [_Resp(400, text="bad")]
    assert await whatsapp.upload_media(b"x") is None


@pytest.mark.asyncio
async def test_send_audio_voice_true_ok() -> None:
    _FakeClient.responses = [_Resp(200, {"messages": [{"id": "wamid.1"}]})]
    ok = await whatsapp.send_audio("5511999998888", "MEDIA123")

    assert ok is True
    assert len(_FakeClient.posts) == 1
    payload = _FakeClient.posts[0]["json"]
    assert payload["type"] == "audio"
    assert payload["audio"] == {"id": "MEDIA123", "voice": True}


@pytest.mark.asyncio
async def test_send_audio_voice_refused_returns_false_no_retry() -> None:
    # voice=true recusado → NÃO faz retry interno (o caller decide o fallback MP3)
    _FakeClient.responses = [_Resp(400, text="voice not supported")]
    ok = await whatsapp.send_audio("5511999998888", "MEDIA123")

    assert ok is False
    assert len(_FakeClient.posts) == 1  # uma tentativa só, sem retry de OGG


@pytest.mark.asyncio
async def test_send_audio_voice_false_sends_plain_audio() -> None:
    # voice=false (fallback MP3) → payload de áudio comum, sem a flag voice
    _FakeClient.responses = [_Resp(200, {})]
    ok = await whatsapp.send_audio("5511999998888", "MP3MEDIA", voice=False)

    assert ok is True
    assert len(_FakeClient.posts) == 1
    assert _FakeClient.posts[0]["json"]["audio"] == {"id": "MP3MEDIA"}

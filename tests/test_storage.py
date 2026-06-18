"""Testes do Supabase Storage (app/storage.py) — httpx mockado."""

from __future__ import annotations

import pytest

from app import storage


class _FakeResp:
    def __init__(self, payload: dict | None = None) -> None:
        self._payload = payload or {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    captured: dict = {}
    response_payload: dict = {}

    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        pass

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *args) -> bool:  # noqa: ANN002
        return False

    async def post(self, url, headers=None, content=None, json=None):  # noqa: ANN001
        _FakeClient.captured = {
            "url": url,
            "headers": headers,
            "content": content,
            "json": json,
        }
        return _FakeResp(_FakeClient.response_payload)


def _configure(monkeypatch) -> None:
    monkeypatch.setattr(storage.settings, "supabase_url", "https://proj.supabase.co")
    monkeypatch.setattr(storage.settings, "supabase_service_key", "svc-key")
    monkeypatch.setattr(storage.settings, "supabase_audio_bucket", "audios")
    monkeypatch.setattr(storage.settings, "audio_url_ttl", 3600)
    monkeypatch.setattr(storage.httpx, "AsyncClient", _FakeClient)


@pytest.mark.asyncio
async def test_upload_audio_posts_and_returns_path(monkeypatch) -> None:
    _configure(monkeypatch)
    path = await storage.upload_audio("5511955554444", b"audio-bytes", "audio/ogg")

    assert path is not None
    assert path.startswith("5511955554444/")
    assert path.endswith(".ogg")
    cap = _FakeClient.captured
    assert "/storage/v1/object/audios/5511955554444/" in cap["url"]
    assert cap["content"] == b"audio-bytes"
    assert cap["headers"]["Authorization"] == "Bearer svc-key"


@pytest.mark.asyncio
async def test_upload_not_configured_returns_none(monkeypatch) -> None:
    monkeypatch.setattr(storage.settings, "supabase_url", "")
    monkeypatch.setattr(storage.settings, "supabase_service_key", "")
    assert await storage.upload_audio("5511", b"bytes", "audio/ogg") is None


@pytest.mark.asyncio
async def test_upload_empty_bytes_returns_none(monkeypatch) -> None:
    _configure(monkeypatch)
    assert await storage.upload_audio("5511", b"", "audio/ogg") is None


@pytest.mark.asyncio
async def test_signed_url_builds_full_url(monkeypatch) -> None:
    _configure(monkeypatch)
    _FakeClient.response_payload = {
        "signedURL": "/object/sign/audios/5511/x.ogg?token=abc"
    }
    url = await storage.signed_url("5511/x.ogg")
    assert url == (
        "https://proj.supabase.co/storage/v1/object/sign/audios/5511/x.ogg?token=abc"
    )
    _FakeClient.response_payload = {}  # limpa pro próximo teste


@pytest.mark.asyncio
async def test_signed_url_none_path_returns_none(monkeypatch) -> None:
    _configure(monkeypatch)
    assert await storage.signed_url(None) is None

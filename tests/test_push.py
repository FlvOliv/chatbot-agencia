"""Testes do envio de push web (Fase 3) — sem banco, sem rede real."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from pywebpush import WebPushException

from app import push


def _sub(endpoint: str):
    return SimpleNamespace(endpoint=endpoint, p256dh="p", auth="a")


def test_push_enabled_reflects_vapid(monkeypatch) -> None:
    monkeypatch.setattr(push.settings, "vapid_public_key", "pub")
    monkeypatch.setattr(push.settings, "vapid_private_key", "priv")
    assert push.push_enabled() is True

    monkeypatch.setattr(push.settings, "vapid_private_key", "")
    assert push.push_enabled() is False


@pytest.mark.asyncio
async def test_send_push_disabled_returns_zero(monkeypatch) -> None:
    """Sem VAPID configurado → não envia nada (e não toca no banco)."""
    monkeypatch.setattr(push.settings, "vapid_public_key", "")
    monkeypatch.setattr(push.settings, "vapid_private_key", "")

    sent = await push.send_push_to_all("oi", "corpo")
    assert sent == 0


@pytest.mark.asyncio
async def test_dispatch_sends_all_and_collects_expired(monkeypatch) -> None:
    """Envia pra cada inscrição; coleta as expiradas (410) pra remoção."""
    enviados: list[tuple[str, str]] = []

    def fake_send_one(sub, payload):  # noqa: ANN001
        if sub.endpoint == "morta":
            raise WebPushException(
                "gone", response=SimpleNamespace(status_code=410)
            )
        enviados.append((sub.endpoint, payload))

    monkeypatch.setattr(push, "_send_one", fake_send_one)

    subs = [_sub("viva-1"), _sub("morta"), _sub("viva-2")]
    payload = json.dumps({"title": "Novo lead #1001", "body": "abrir"})

    sent, expired = await push._dispatch(subs, payload)

    assert sent == 2
    assert expired == ["morta"]
    assert {e for e, _ in enviados} == {"viva-1", "viva-2"}


@pytest.mark.asyncio
async def test_dispatch_other_errors_dont_expire(monkeypatch) -> None:
    """Erro que não é 404/410 não marca a inscrição pra remoção."""

    def fake_send_one(sub, payload):  # noqa: ANN001
        raise WebPushException(
            "server error", response=SimpleNamespace(status_code=500)
        )

    monkeypatch.setattr(push, "_send_one", fake_send_one)

    sent, expired = await push._dispatch([_sub("x")], "{}")

    assert sent == 0
    assert expired == []

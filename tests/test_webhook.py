"""Testes dos endpoints /webhook e /health."""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(
        settings.wa_app_secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_webhook_verify_ok(client: TestClient) -> None:
    r = client.get(
        "/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.challenge": "challenge-xyz",
            "hub.verify_token": settings.wa_verify_token,
        },
    )
    assert r.status_code == 200
    assert r.text == "challenge-xyz"


def test_webhook_verify_wrong_token(client: TestClient) -> None:
    r = client.get(
        "/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.challenge": "x",
            "hub.verify_token": "WRONG",
        },
    )
    assert r.status_code == 403


def test_webhook_post_invalid_signature(client: TestClient) -> None:
    body = json.dumps({"object": "whatsapp_business_account"}).encode("utf-8")
    r = client.post(
        "/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": "sha256=deadbeef",
        },
    )
    assert r.status_code == 401


def test_webhook_post_valid_signature_calls_handler(client: TestClient) -> None:
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "5511000000001",
                                    "type": "text",
                                    "text": {"body": "oi"},
                                }
                            ]
                        }
                    }
                ]
            }
        ],
    }
    body = json.dumps(payload).encode("utf-8")

    with patch("app.main.handle_message") as mock_handle:
        r = client.post(
            "/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": _sign(body),
            },
        )

    assert r.status_code == 200
    # BackgroundTasks dispara após response — verifica que foi enfileirado
    assert mock_handle.called


def test_webhook_post_no_signature_header(client: TestClient) -> None:
    body = json.dumps({"object": "x"}).encode("utf-8")
    r = client.post(
        "/webhook",
        content=body,
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 401

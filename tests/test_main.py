"""Testes do pipeline principal (app/main.py)."""

from __future__ import annotations

import pytest

from app import main


@pytest.mark.asyncio
async def test_ai_failure_silences_and_calls_lu(monkeypatch) -> None:
    """As duas IAs caíram → Malu avisa UMA vez, silencia e chama a Lu.

    Garante o anti-repetição: marca STATE_TRANSFERRED (Malu cala nos próximos
    turnos), manda a mensagem única pro cliente e notifica a Lu.
    """
    calls: dict[str, object] = {}

    async def fake_set_state(phone, state):  # noqa: ANN001
        calls["state"] = state

    async def fake_cancel(phone):  # noqa: ANN001
        calls["cancel"] = phone

    async def fake_send(to, text):  # noqa: ANN001
        calls["sent_to"] = to
        calls["sent_text"] = text
        return True

    async def fake_persist(phone, user_text, reply, model):  # noqa: ANN001
        calls["persist_model"] = model

    async def fake_notify(phone, name):  # noqa: ANN001
        calls["notified"] = (phone, name)
        return True

    monkeypatch.setattr(main, "set_state", fake_set_state)
    monkeypatch.setattr(main, "cancel_reminders", fake_cancel)
    monkeypatch.setattr(main, "send_message", fake_send)
    monkeypatch.setattr(main, "_persist_conversation", fake_persist)
    monkeypatch.setattr(main, "notify_luciana_ai_down", fake_notify)

    await main._handle_ai_failure("5511955554444", "oi", "João")

    assert calls["state"] == main.STATE_TRANSFERRED  # Malu silencia depois
    assert calls["sent_text"] == main.IA_FALHA_REPLY  # mensagem única pro cliente
    assert calls["sent_to"] == "5511955554444"
    assert calls["persist_model"] == "flow:ai-failure"
    assert calls["notified"] == ("5511955554444", "João")  # Lu avisada


def test_closing_reply_sempre_tem_cta() -> None:
    """Toda finalização leva o CTA: Instagram + grupo VIP (#7)."""
    reply = main._build_closing_reply(None)
    assert "instagram.com/lumilhaseviagens" in reply
    assert "chat.whatsapp.com/" in reply
    assert "Protocolo" not in reply  # sem número → sem linha de protocolo


def test_closing_reply_inclui_protocolo() -> None:
    reply = main._build_closing_reply(1007)
    assert "#1007" in reply
    assert "instagram.com/lumilhaseviagens" in reply
    assert "chat.whatsapp.com/" in reply

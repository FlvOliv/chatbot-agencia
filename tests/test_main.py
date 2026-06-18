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


@pytest.mark.asyncio
async def test_audio_disabled_falls_back_to_handoff(monkeypatch) -> None:
    """Transcrição DESLIGADA → áudio segue o handoff de hoje (acolhe + Lu)."""
    calls: dict[str, object] = {}

    async def fake_media(phone, profile, media_type):  # noqa: ANN001
        calls["handoff"] = (phone, profile, media_type)

    async def fake_process(*args, **kwargs):  # noqa: ANN002, ANN003
        calls["processed"] = True

    monkeypatch.setattr(main.settings, "audio_transcription_enabled", False)
    monkeypatch.setattr(main, "_handle_media_message", fake_media)
    monkeypatch.setattr(main, "_process_text_message", fake_process)

    await main._handle_audio_message("5511955554444", "João", "media_id_1")

    assert calls["handoff"] == ("5511955554444", "João", "audio")
    assert "processed" not in calls  # nunca chega na IA


@pytest.mark.asyncio
async def test_audio_success_flows_as_text_from_audio(monkeypatch) -> None:
    """Transcrição OK → fluxo de texto com from_audio=True + media_path do áudio."""
    calls: dict[str, object] = {}

    async def fake_download(media_id):  # noqa: ANN001
        return b"bytes", "audio/ogg"

    async def fake_upload(phone, audio_bytes, mime):  # noqa: ANN001
        return "5511955554444/abc.ogg"

    async def fake_transcribe(audio_bytes, mime):  # noqa: ANN001
        return "quero ir pra Bariloche"

    async def fake_process(phone, user_text, profile, from_audio=False, media_path=None):  # noqa: ANN001
        calls["args"] = (phone, user_text, profile, from_audio, media_path)

    async def fake_media(*args, **kwargs):  # noqa: ANN002, ANN003
        calls["handoff"] = True

    monkeypatch.setattr(main.settings, "audio_transcription_enabled", True)
    monkeypatch.setattr(main, "download_media", fake_download)
    monkeypatch.setattr(main, "upload_audio", fake_upload)
    monkeypatch.setattr(main, "transcribe_audio", fake_transcribe)
    monkeypatch.setattr(main, "_process_text_message", fake_process)
    monkeypatch.setattr(main, "_handle_media_message", fake_media)

    await main._handle_audio_message("5511955554444", "João", "media_id_1")

    assert calls["args"] == (
        "5511955554444", "quero ir pra Bariloche", "João", True, "5511955554444/abc.ogg"
    )
    assert "handoff" not in calls  # não passa pra Lu — a Malu segue


@pytest.mark.asyncio
async def test_audio_transcribe_error_falls_back_to_handoff(monkeypatch) -> None:
    """Erro no download → handoff seguro pra Lu (cliente nunca no vácuo)."""
    calls: dict[str, object] = {}

    async def fake_download(media_id):  # noqa: ANN001
        raise RuntimeError("boom")

    async def fake_process(*args, **kwargs):  # noqa: ANN002, ANN003
        calls["processed"] = True

    async def fake_media(phone, profile, media_type, media_path=None):  # noqa: ANN001
        calls["handoff"] = (phone, profile, media_type, media_path)

    monkeypatch.setattr(main.settings, "audio_transcription_enabled", True)
    monkeypatch.setattr(main, "download_media", fake_download)
    monkeypatch.setattr(main, "_process_text_message", fake_process)
    monkeypatch.setattr(main, "_handle_media_message", fake_media)

    await main._handle_audio_message("5511955554444", "João", "media_id_1")

    # Download falhou antes do upload → sem áudio guardado (media_path None).
    assert calls["handoff"] == ("5511955554444", "João", "audio", None)
    assert "processed" not in calls


@pytest.mark.asyncio
async def test_audio_empty_transcript_handoff_keeps_audio(monkeypatch) -> None:
    """Transcrição vazia → handoff, MAS o áudio guardado segue (Lu pode ouvir)."""
    calls: dict[str, object] = {}

    async def fake_download(media_id):  # noqa: ANN001
        return b"bytes", "audio/ogg"

    async def fake_upload(phone, audio_bytes, mime):  # noqa: ANN001
        return "5511955554444/abc.ogg"

    async def fake_transcribe(audio_bytes, mime):  # noqa: ANN001
        return "   "

    async def fake_process(*args, **kwargs):  # noqa: ANN002, ANN003
        calls["processed"] = True

    async def fake_media(phone, profile, media_type, media_path=None):  # noqa: ANN001
        calls["handoff"] = (phone, profile, media_type, media_path)

    monkeypatch.setattr(main.settings, "audio_transcription_enabled", True)
    monkeypatch.setattr(main, "download_media", fake_download)
    monkeypatch.setattr(main, "upload_audio", fake_upload)
    monkeypatch.setattr(main, "transcribe_audio", fake_transcribe)
    monkeypatch.setattr(main, "_process_text_message", fake_process)
    monkeypatch.setattr(main, "_handle_media_message", fake_media)

    await main._handle_audio_message("5511955554444", "João", "media_id_1")

    # Handoff recebeu o media_path → áudio fica ouvível no painel mesmo sem texto.
    assert calls["handoff"] == ("5511955554444", "João", "audio", "5511955554444/abc.ogg")
    assert "processed" not in calls


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

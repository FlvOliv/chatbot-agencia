"""Testes do pipeline principal (app/main.py)."""

from __future__ import annotations

from types import SimpleNamespace

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

    async def fake_transcode(audio_bytes):  # noqa: ANN001
        return None  # sem ffmpeg → sobe o original (não importa pro assert)

    async def fake_transcribe(audio_bytes, mime):  # noqa: ANN001
        return "quero ir pra Bariloche"

    async def fake_process(phone, user_text, profile, from_audio=False, media_path=None):  # noqa: ANN001
        calls["args"] = (phone, user_text, profile, from_audio, media_path)

    async def fake_media(*args, **kwargs):  # noqa: ANN002, ANN003
        calls["handoff"] = True

    monkeypatch.setattr(main.settings, "audio_transcription_enabled", True)
    monkeypatch.setattr(main, "download_media", fake_download)
    monkeypatch.setattr(main, "transcode_to_mp3", fake_transcode)
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
async def test_audio_transcodes_to_mp3_before_upload(monkeypatch) -> None:
    """ffmpeg OK → guarda o MP3 (audio/mpeg), não o OGG original."""
    calls: dict[str, object] = {}

    async def fake_download(media_id):  # noqa: ANN001
        return b"ogg-bytes", "audio/ogg"

    async def fake_transcode(audio_bytes):  # noqa: ANN001
        return b"mp3-bytes"

    async def fake_upload(phone, audio_bytes, mime):  # noqa: ANN001
        calls["upload"] = (audio_bytes, mime)
        return "5511955554444/abc.mp3"

    async def fake_transcribe(audio_bytes, mime):  # noqa: ANN001
        return "oi"

    async def fake_process(*args, **kwargs):  # noqa: ANN002, ANN003
        calls["media_path"] = kwargs.get("media_path")

    monkeypatch.setattr(main.settings, "audio_transcription_enabled", True)
    monkeypatch.setattr(main, "download_media", fake_download)
    monkeypatch.setattr(main, "transcode_to_mp3", fake_transcode)
    monkeypatch.setattr(main, "upload_audio", fake_upload)
    monkeypatch.setattr(main, "transcribe_audio", fake_transcribe)
    monkeypatch.setattr(main, "_process_text_message", fake_process)

    await main._handle_audio_message("5511955554444", "João", "media_id_1")

    # Subiu o MP3 convertido (não o OGG), com o mime certo.
    assert calls["upload"] == (b"mp3-bytes", "audio/mpeg")
    assert calls["media_path"] == "5511955554444/abc.mp3"


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

    async def fake_transcode(audio_bytes):  # noqa: ANN001
        return None

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
    monkeypatch.setattr(main, "transcode_to_mp3", fake_transcode)
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


@pytest.mark.asyncio
async def test_extraction_none_does_not_finalize(monkeypatch) -> None:
    """Fail-CLOSED: o modelo emitiu '## Resumo' mas a extração (2ª chamada de IA)
    voltou None → o gate não pode validar a coleta → NÃO finaliza lead furado;
    manda o nudge de completude e segue coletando (re-checa no próximo turno).
    """
    calls: dict[str, object] = {}

    async def fake_get_state(phone):  # noqa: ANN001
        return ""

    async def fake_get_history(phone):  # noqa: ANN001
        # Indicação JÁ perguntada → prova que o bloqueio vem da extração vazia,
        # não de um campo faltando por acaso.
        return [
            {"role": "user", "content": "quero cotar uma viagem"},
            {"role": "assistant", "content": "Alguém indicou a Lu pra você? 💛"},
        ]

    class _FakeDB:
        async def commit(self):  # noqa: ANN001
            pass

    class _FakeSession:
        async def __aenter__(self):  # noqa: ANN001
            return _FakeDB()

        async def __aexit__(self, *a):  # noqa: ANN001
            return False

    async def fake_get_or_create(phone, profile, db):  # noqa: ANN001
        return SimpleNamespace(display_name="João")

    async def fake_route_and_ask(history, customer_context=None):  # noqa: ANN001
        return ("Perfeito, vou organizar tudo!\n## Resumo", "groq/llama")

    def fake_split_briefing(reply):  # noqa: ANN001
        # Parser testado isoladamente em test_briefing.py → aqui só sinaliza fecho.
        return "Perfeito, vou organizar tudo!", "## Resumo da Solicitação"

    async def fake_extract(history):  # noqa: ANN001
        return None  # <- caso sob teste: extração capotou

    async def fail_finalize(*a, **k):  # noqa: ANN001
        calls["finalized"] = True  # NÃO pode ser chamado
        return 1

    async def fake_send(to, text):  # noqa: ANN001
        calls["sent"] = text
        return True

    async def fake_save_history(phone, history):  # noqa: ANN001
        calls["saved_last"] = history[-1]["content"]

    async def fake_persist(*a, **k):  # noqa: ANN001
        pass

    async def fake_schedule(phone, name=None):  # noqa: ANN001
        calls["rescheduled"] = True

    monkeypatch.setattr(main, "get_state", fake_get_state)
    monkeypatch.setattr(main, "get_history", fake_get_history)
    monkeypatch.setattr(main, "SessionLocal", _FakeSession)
    monkeypatch.setattr(main, "get_or_create_cliente", fake_get_or_create)
    monkeypatch.setattr(main, "route_and_ask", fake_route_and_ask)
    monkeypatch.setattr(main, "split_reply_and_briefing", fake_split_briefing)
    monkeypatch.setattr(main, "extract_lead_data", fake_extract)
    monkeypatch.setattr(main, "_finalize_lead", fail_finalize)
    monkeypatch.setattr(main, "send_message", fake_send)
    monkeypatch.setattr(main, "save_history", fake_save_history)
    monkeypatch.setattr(main, "_persist_conversation", fake_persist)
    monkeypatch.setattr(main, "schedule_callbacks", fake_schedule)

    await main._process_text_message(
        "5511955551111", "fecha aí então", "João", from_audio=True
    )

    assert "finalized" not in calls  # fail-closed: NÃO finalizou o lead
    assert "💛" in str(calls["sent"])  # mandou o nudge de completude
    assert calls["saved_last"] == calls["sent"]  # nudge entrou no histórico
    assert calls.get("rescheduled") is True  # coleta segue aberta (re-arma lembrete)

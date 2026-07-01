"""Testes do B3 — resolução de tenant + roteamento por phone_number_id."""

from __future__ import annotations

import uuid

import pytest
from cryptography.fernet import Fernet

from app import ai, briefing, crypto, main, whatsapp
from app import tenant as tenant_mod
from app.config import settings
from app.tenant import TenantContext
from app.whatsapp import detect_phone_number_id


def _payload(pid: str | None) -> dict:
    meta = {"phone_number_id": pid} if pid is not None else {}
    return {"entry": [{"changes": [{"value": {"metadata": meta}}]}]}


def _ctx(
    nome: str = "Lu",
    *,
    owner_phone: str = "5511999999999",
    wa_phone_id: str = "1080643978473403",
    wa_token_enc: str = "enc",
    brand: dict | None = None,
    prompt_overrides: dict | None = None,
) -> TenantContext:
    return TenantContext(
        id=uuid.uuid4(),
        nome=nome,
        wa_phone_id=wa_phone_id,
        wa_token_enc=wa_token_enc,
        owner_phone=owner_phone,
        business_hours_start=9,
        business_hours_end=18,
        brand=brand or {},
        prompt_overrides=prompt_overrides or {},
    )


@pytest.fixture(autouse=True)
def _reset_tenant_state():
    tenant_mod.clear_tenant_cache()
    tenant_mod.set_current_tenant(None)
    yield
    tenant_mod.clear_tenant_cache()
    tenant_mod.set_current_tenant(None)


def test_detect_phone_number_id_presente() -> None:
    assert detect_phone_number_id(_payload("123456")) == "123456"


def test_detect_phone_number_id_ausente() -> None:
    assert detect_phone_number_id(_payload(None)) is None
    assert detect_phone_number_id({}) is None
    assert detect_phone_number_id({"entry": [{"changes": []}]}) is None


@pytest.mark.asyncio
async def test_resolve_tenant_usa_cache(monkeypatch) -> None:
    """2ª chamada com o mesmo pid não toca o banco (cache curto)."""
    chamadas = {"n": 0}
    ctx = _ctx()

    async def fake_load(pid):  # noqa: ANN001
        chamadas["n"] += 1
        return ctx

    monkeypatch.setattr(tenant_mod, "_load", fake_load)
    r1 = await tenant_mod.resolve_tenant("p1")
    r2 = await tenant_mod.resolve_tenant("p1")
    assert r1 is ctx and r2 is ctx
    assert chamadas["n"] == 1  # a 2ª veio do cache


@pytest.mark.asyncio
async def test_resolve_tenant_none_quando_load_none(monkeypatch) -> None:
    async def fake_load(pid):  # noqa: ANN001
        return None

    monkeypatch.setattr(tenant_mod, "_load", fake_load)
    assert await tenant_mod.resolve_tenant("x") is None


def test_current_tenant_contextvar() -> None:
    ctx = _ctx("Agência B")
    assert tenant_mod.get_current_tenant() is None
    tenant_mod.set_current_tenant(ctx)
    assert tenant_mod.get_current_tenant() is ctx


@pytest.mark.asyncio
async def test_handle_message_arma_contexto_do_tenant(monkeypatch) -> None:
    """handle_message resolve a agência e arma o contexto ANTES do dispatch.

    Payload sem mensagens retorna cedo — mas a resolução já aconteceu, provando a
    fiação (B3) sem mudar o comportamento do caminho de mensagem.
    """
    ctx = _ctx("Agência X")

    async def fake_resolve(pid):  # noqa: ANN001
        return ctx

    monkeypatch.setattr(main, "resolve_tenant", fake_resolve)
    await main.handle_message(
        {"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": "p"}, "messages": []}}]}]}
    )
    assert tenant_mod.get_current_tenant() is ctx


# --- B4: I/O parametrizado por tenant ---------------------------------------
def test_closing_reply_usa_brand_do_tenant() -> None:
    """Com tenant, o CTA usa os links da agência (não os da Lu)."""
    tenant_mod.set_current_tenant(
        _ctx(
            "Agência B",
            brand={
                "instagram": "https://instagram.com/agenciaB",
                "grupo_vip": "https://chat.whatsapp.com/BBBBB",
            },
        )
    )
    reply = main._build_closing_reply(None)
    assert "instagram.com/agenciaB" in reply
    assert "chat.whatsapp.com/BBBBB" in reply
    assert "lumilhaseviagens" not in reply


def test_closing_reply_fallback_sem_tenant() -> None:
    """Sem tenant → texto/links padrão da Lu (comportamento de hoje)."""
    reply = main._build_closing_reply(None)
    assert "instagram.com/lumilhaseviagens" in reply


def test_owner_phone_usa_tenant() -> None:
    tenant_mod.set_current_tenant(_ctx(owner_phone="5511888887777"))
    assert briefing._owner_phone() == "5511888887777"


def test_owner_phone_fallback_global() -> None:
    tenant_mod.set_current_tenant(None)
    assert briefing._owner_phone() == settings.luciana_phone


def test_system_prompt_anexa_override_da_agencia() -> None:
    tenant_mod.set_current_tenant(
        _ctx(prompt_overrides={"system_extra": "REGRA EXCLUSIVA DA AGENCIA B"})
    )
    prompt = ai._build_system_prompt(None)
    assert "Ajustes da agência" in prompt
    assert "REGRA EXCLUSIVA DA AGENCIA B" in prompt


def test_tenant_creds_decifra_token_do_tenant(monkeypatch) -> None:
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(whatsapp.settings, "tenant_secret_key", key)
    crypto._fernet.cache_clear()
    try:
        enc = crypto.encrypt("TENANT_TOKEN_XYZ")
        tenant_mod.set_current_tenant(_ctx(wa_phone_id="999000", wa_token_enc=enc))
        pid, tok = whatsapp._tenant_creds()
        assert pid == "999000"
        assert tok == "TENANT_TOKEN_XYZ"
    finally:
        crypto._fernet.cache_clear()


def test_tenant_creds_fallback_quando_token_indecifravel() -> None:
    """Token quebrado/chave errada → cai pras credenciais globais, sem derrubar."""
    tenant_mod.set_current_tenant(_ctx(wa_token_enc="lixo-nao-fernet"))
    pid, tok = whatsapp._tenant_creds()
    assert pid == settings.wa_phone_id
    assert tok == settings.wa_token


# --- B5: escritas carimbam tenant_id ----------------------------------------
def test_current_tenant_id() -> None:
    assert tenant_mod.current_tenant_id() is None
    ctx = _ctx()
    tenant_mod.set_current_tenant(ctx)
    assert tenant_mod.current_tenant_id() == ctx.id


class _FakeDB:
    """Sessão mínima pra capturar o objeto gravado (sem banco real)."""

    def __init__(self) -> None:
        self.added: object | None = None
        self.added_all: list | None = None

    def add(self, obj) -> None:  # noqa: ANN001
        self.added = obj

    def add_all(self, objs) -> None:  # noqa: ANN001
        self.added_all = list(objs)

    async def flush(self) -> None:
        pass

    async def refresh(self, obj) -> None:  # noqa: ANN001
        pass

    async def commit(self) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a) -> bool:  # noqa: ANN002
        return False


@pytest.mark.asyncio
async def test_save_lead_carimba_tenant_id() -> None:
    ctx = _ctx("Agência B")
    tenant_mod.set_current_tenant(ctx)
    db = _FakeDB()
    await briefing.save_lead("5511955554444", db, briefing_md="x", lead_temp="frio")
    assert db.added.tenant_id == ctx.id


@pytest.mark.asyncio
async def test_save_lead_sem_tenant_fica_none() -> None:
    tenant_mod.set_current_tenant(None)
    db = _FakeDB()
    await briefing.save_lead("5511955554444", db, briefing_md="x", lead_temp="frio")
    assert db.added.tenant_id is None


@pytest.mark.asyncio
async def test_persist_conversation_carimba_tenant(monkeypatch) -> None:
    ctx = _ctx("Agência B")
    tenant_mod.set_current_tenant(ctx)
    db = _FakeDB()
    monkeypatch.setattr(main, "SessionLocal", lambda: db)
    await main._persist_conversation("5511955554444", "oi", "olá", "model-x")
    assert db.added_all is not None and len(db.added_all) == 2
    assert all(o.tenant_id == ctx.id for o in db.added_all)


# --- B7a: tenant na API (bind_tenant + tenant_filter + carimbo de escrita) ---
@pytest.mark.asyncio
async def test_bind_tenant_default_sem_header(monkeypatch) -> None:
    from app.api import deps

    ctx = _ctx("default-lu")

    async def fake_resolve(pid):  # noqa: ANN001
        return ctx

    monkeypatch.setattr(deps, "resolve_tenant", fake_resolve)
    await deps.bind_tenant(None)
    assert tenant_mod.get_current_tenant() is ctx


@pytest.mark.asyncio
async def test_bind_tenant_usa_header(monkeypatch) -> None:
    from app.api import deps

    ctx = _ctx("Agência B")

    async def fake_by_id(tid):  # noqa: ANN001
        return ctx

    async def fake_resolve(pid):  # noqa: ANN001
        return _ctx("default")

    monkeypatch.setattr(deps, "resolve_tenant_by_id", fake_by_id)
    monkeypatch.setattr(deps, "resolve_tenant", fake_resolve)
    await deps.bind_tenant(str(uuid.uuid4()))
    assert tenant_mod.get_current_tenant() is ctx


def test_tenant_filter_sem_tenant_nao_filtra() -> None:
    from app.models import Lead

    assert "true" in str(tenant_mod.tenant_filter(Lead)).lower()


def test_tenant_filter_com_tenant_gera_or_null_tolerante() -> None:
    from app.models import Lead

    tenant_mod.set_current_tenant(_ctx())
    clause = str(tenant_mod.tenant_filter(Lead))
    assert "tenant_id" in clause
    assert "IS NULL" in clause.upper()  # tolera NULL na transição


@pytest.mark.asyncio
async def test_create_lead_route_carimba_tenant() -> None:
    from app.api import leads as leads_api
    from app.api.schemas import LeadIn

    ctx = _ctx("Agência B")
    tenant_mod.set_current_tenant(ctx)
    db = _FakeDB()
    await leads_api.create_lead(LeadIn(phone="5511955554444"), db)
    assert db.added.tenant_id == ctx.id


# --- B7a-2: read-scoping — os padrões difíceis compilam pra SQL válido --------
def test_tenant_filter_compila_subquery_e_agregacao() -> None:
    """Prova (sem DB) que `tenant_filter` gera SQL Postgres válido nos 2 padrões
    mais arriscados do read-scoping: subquery+group_by (list_conversations) e
    agregação com count (metrics). Validação semântica real fica pra staging."""
    from datetime import datetime, timezone

    from sqlalchemy import func, select
    from sqlalchemy.dialects import postgresql

    from app.models import Conversation, Lead

    tenant_mod.set_current_tenant(_ctx())

    subq = (
        select(Conversation.phone, func.count(Conversation.id))
        .where(tenant_mod.tenant_filter(Conversation))
        .group_by(Conversation.phone)
        .subquery()
    )
    sql_sub = str(select(subq.c.phone).compile(dialect=postgresql.dialect()))

    agg = select(func.count(Lead.id)).where(
        Lead.created_at >= datetime.now(timezone.utc),
        tenant_mod.tenant_filter(Lead),
    )
    sql_agg = str(agg.compile(dialect=postgresql.dialect()))

    assert "tenant_id" in sql_sub.lower()
    assert "tenant_id" in sql_agg.lower()

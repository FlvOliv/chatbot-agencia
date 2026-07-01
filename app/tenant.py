"""Resolução do tenant (agência) por número de WhatsApp + contexto da request.

O webhook descobre a agência pelo `phone_number_id` (metadata da Meta). Resolvido
1× por mensagem em `handle_message` e guardado num ContextVar request-scoped que
os módulos de saída/consulta leem (B4/B5) — sem precisar costurar o tenant como
parâmetro por toda a cadeia.

ContextVar é async-safe: cada webhook roda como task isolada (BackgroundTasks) e
`asyncio.create_task` COPIA o contexto atual → o valor propaga pros filhos sem
vazar entre requests concorrentes. Desconhecido/None → tenant default (a agência
mais antiga = a Lu), pra manter o número único de hoje funcionando enquanto a
fundação é montada.
"""

from __future__ import annotations

import logging
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass

from sqlalchemy import or_, select, true

from app.database import SessionLocal
from app.models import Agencia

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TenantContext:
    """Snapshot imutável da agência — desacoplado da sessão ORM (sem lazy-load).

    Carrega só o que o caminho de mensagem precisa (B4): id pra filtrar queries,
    credenciais de envio, telefone do dono, marca e overrides de prompt.
    """

    id: uuid.UUID
    nome: str
    wa_phone_id: str
    wa_token_enc: str
    owner_phone: str
    business_hours_start: int
    business_hours_end: int
    brand: dict
    prompt_overrides: dict


def _from_row(a: Agencia) -> TenantContext:
    return TenantContext(
        id=a.id,
        nome=a.nome,
        wa_phone_id=a.wa_phone_id,
        wa_token_enc=a.wa_token_enc,
        owner_phone=a.owner_phone,
        business_hours_start=a.business_hours_start,
        business_hours_end=a.business_hours_end,
        brand=dict(a.brand or {}),
        prompt_overrides=dict(a.prompt_overrides or {}),
    )


# Cache curto por phone_number_id (evita 1 query por mensagem). TTL pequeno —
# mudanças na agência aparecem em até _CACHE_TTL segundos.
_CACHE: dict[str | None, tuple[float, "TenantContext | None"]] = {}
_CACHE_TTL = 60.0


def clear_tenant_cache() -> None:
    """Limpa o cache de resolução (usado em testes e após editar uma agência)."""
    _CACHE.clear()


async def _load(phone_number_id: str | None) -> TenantContext | None:
    try:
        async with SessionLocal() as s:
            if phone_number_id:
                row = (
                    await s.execute(
                        select(Agencia).where(
                            Agencia.wa_phone_id == phone_number_id,
                            Agencia.ativo.is_(True),
                        )
                    )
                ).scalar_one_or_none()
                if row is not None:
                    return _from_row(row)
            # Default: agência mais antiga (a Lu) — mantém o número único de hoje.
            row = (
                await s.execute(
                    select(Agencia)
                    .where(Agencia.ativo.is_(True))
                    .order_by(Agencia.created_at.asc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            return _from_row(row) if row is not None else None
    except Exception:
        logger.warning(
            "resolve_tenant: falha ao resolver tenant (pid=%s) — seguindo com None",
            phone_number_id,
        )
        return None


async def resolve_tenant(phone_number_id: str | None) -> TenantContext | None:
    """Resolve a agência pelo phone_number_id (com cache curto). None se não achar."""
    now = time.monotonic()
    hit = _CACHE.get(phone_number_id)
    if hit is not None and now - hit[0] < _CACHE_TTL:
        return hit[1]
    tenant = await _load(phone_number_id)
    _CACHE[phone_number_id] = (now, tenant)
    return tenant


async def resolve_tenant_by_id(tenant_id: uuid.UUID) -> TenantContext | None:
    """Resolve a agência pelo seu id (usado pelo painel via header — B7)."""
    try:
        async with SessionLocal() as s:
            row = (
                await s.execute(
                    select(Agencia).where(
                        Agencia.id == tenant_id, Agencia.ativo.is_(True)
                    )
                )
            ).scalar_one_or_none()
            return _from_row(row) if row is not None else None
    except Exception:
        logger.warning("resolve_tenant_by_id: falha (%s) — seguindo com None", tenant_id)
        return None


# --- Contexto request-scoped ------------------------------------------------
_current_tenant: ContextVar[TenantContext | None] = ContextVar(
    "current_tenant", default=None
)


def set_current_tenant(tenant: TenantContext | None) -> None:
    """Define o tenant da request atual (chamado 1× no topo de handle_message)."""
    _current_tenant.set(tenant)


def get_current_tenant() -> TenantContext | None:
    """Lê o tenant da request atual (usado pelos módulos de saída/consulta)."""
    return _current_tenant.get()


def current_tenant_id() -> uuid.UUID | None:
    """ID do tenant atual, ou None — atalho pra CARIMBAR escritas por agência (B5).

    None (sem contexto: testes, painel pré-B7, cron pré-B7, ou agência ainda não
    seedada) → a coluna `tenant_id` fica NULL (= comportamento de hoje). Nenhuma
    leitura filtra por isso ainda (read-scoping é B7), então carimbar é uma
    mudança invisível: só garante que o dado nasce atribuído à agência certa.
    """
    tenant = _current_tenant.get()
    return tenant.id if tenant is not None else None


def tenant_filter(model):  # noqa: ANN001, ANN201
    """Cláusula WHERE de leitura por tenant — TOLERANTE A NULL (transição pré-B6).

    Sem tenant resolvido no contexto → sempre-verdadeiro (não filtra: igual a
    hoje). Com tenant → casa as linhas da agência E as ainda-NULL (legado/escritas
    não carimbadas), pra nada sumir do painel durante a transição. Quando o B6
    tornar `tenant_id` NOT NULL (sem NULLs restantes), o ramo IS NULL fica inócuo.
    """
    tid = current_tenant_id()
    if tid is None:
        return true()
    return or_(model.tenant_id == tid, model.tenant_id.is_(None))

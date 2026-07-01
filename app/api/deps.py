"""Dependencies compartilhadas das rotas /api/* — vínculo de tenant (B7a).

`bind_tenant` roda em toda rota do painel e arma o tenant da request no
ContextVar (mesmo mecanismo do webhook, B3). As queries/escritas das rotas leem
isso via `current_tenant_id()` / `tenant_filter()`.
"""

from __future__ import annotations

import uuid

from fastapi import Header

from app.tenant import resolve_tenant, resolve_tenant_by_id, set_current_tenant


async def bind_tenant(
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
) -> None:
    """Resolve a agência da request do painel e arma o contexto.

    `X-Tenant-Id` é setado pelo servidor Next.js conforme o usuário logado (B7b).
    Ausente/ inválido → agência default (a mais antiga = a Lu), pra o painel de
    hoje (1 número, sem header) seguir funcionando sem mudança.
    """
    tenant = None
    if x_tenant_id:
        try:
            tenant = await resolve_tenant_by_id(uuid.UUID(x_tenant_id))
        except ValueError:
            tenant = None
    if tenant is None:
        tenant = await resolve_tenant(None)  # default (mais antiga), cacheado
    set_current_tenant(tenant)

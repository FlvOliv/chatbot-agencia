"""Autenticação simples por API key — dependency das rotas /api/*."""

from __future__ import annotations

from fastapi import Header, HTTPException, status

from app.config import settings


async def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    """Valida o header `X-API-Key` contra `CRM_API_KEY` do .env.

    Se `CRM_API_KEY` estiver vazia, bloqueia todas as rotas (fail-safe).
    Em produção, troque por JWT/OAuth quando tiver mais de 1 cliente.
    """
    expected = settings.crm_api_key
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API key não configurada no servidor (CRM_API_KEY vazia)",
        )
    if not x_api_key or x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-API-Key inválida ou ausente",
        )

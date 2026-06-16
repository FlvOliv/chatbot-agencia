"""Rota /api/config — configuração não-secreta exibida no painel.

FONTE ÚNICA da verdade: o painel lê daqui, em vez de duplicar os valores em
variáveis `NEXT_PUBLIC_*`. Nunca expõe segredos (tokens, chaves, URLs de banco).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app import __version__
from app.api.auth import require_api_key
from app.api.schemas import AppConfigOut
from app.config import settings

router = APIRouter(
    prefix="/config",
    tags=["config"],
    dependencies=[Depends(require_api_key)],
)


@router.get("", response_model=AppConfigOut)
async def get_config() -> AppConfigOut:
    """Config operacional não-secreta (telefone da Lu, IA, horário comercial)."""
    return AppConfigOut(
        luciana_phone=settings.luciana_phone,
        ai_primary=settings.ai_primary,
        ai_fallback=settings.ai_fallback,
        business_hours_start=settings.business_hours_start,
        business_hours_end=settings.business_hours_end,
        app_env=settings.app_env,
        version=__version__,
        vapid_public_key=settings.vapid_public_key,
    )

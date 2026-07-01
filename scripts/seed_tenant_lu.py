"""Seed idempotente do tenant 1 (Lu Milhas) na tabela `agencias`.

Roda 1× DEPOIS da migration 0012, fora do boot automático (precisa da
TENANT_SECRET_KEY pra cifrar o token). Lê o número único de hoje do `.env`
(`settings`), cifra o `wa_token` (app/crypto.py) e cria a agência da Lu.
Re-rodar é seguro: faz upsert por `wa_phone_id`.

Uso (Windows / venv):
    PYTHONUTF8=1 venv\\Scripts\\python -m scripts.seed_tenant_lu

Pré-requisitos: `TENANT_SECRET_KEY` setada no ambiente + migration 0012 aplicada.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.config import settings
from app.crypto import encrypt
from app.database import SessionLocal, dispose_engine
from app.models import Agencia

# Marca da Lu — hoje hardcoded em app/main.py (COLETA_CONCLUIDA_REPLY). Migra pra
# cá como dado do tenant; o código passa a ler de `agencia.brand` no bloco B4.
LU_BRAND = {
    "nome_marca": "Lu Milhas e Viagens",
    "instagram": "https://instagram.com/lumilhaseviagens",
    "grupo_vip": "https://chat.whatsapp.com/KkWYCAtn3z46bg8W0rK4oc",
}


async def main() -> None:
    if not settings.wa_phone_id or not settings.wa_token:
        raise SystemExit("[seed] WA_PHONE_ID / WA_TOKEN ausentes no ambiente — abortando")

    async with SessionLocal() as session:
        existing = (
            await session.execute(
                select(Agencia).where(Agencia.wa_phone_id == settings.wa_phone_id)
            )
        ).scalar_one_or_none()

        if existing is not None:
            print(
                f"[seed] agência já existe id={existing.id} "
                f"wa_phone_id={existing.wa_phone_id} — nada a fazer (idempotente)"
            )
            return

        agencia = Agencia(
            nome="Lu Milhas e Viagens",
            wa_phone_id=settings.wa_phone_id,
            wa_token_enc=encrypt(settings.wa_token),
            owner_phone=settings.luciana_phone,
            business_hours_start=settings.business_hours_start,
            business_hours_end=settings.business_hours_end,
            brand=LU_BRAND,
        )
        session.add(agencia)
        await session.commit()
        await session.refresh(agencia)
        print(f"[seed] tenant 1 criado: id={agencia.id} nome={agencia.nome!r}")

    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())

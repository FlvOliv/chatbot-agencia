"""Verifica se o ambiente está pronto para rodar a Malu.

Uso:
    python scripts/check_setup.py

Checa o provider de IA ativo (Gemini ou Groq) conforme `AI_PRIMARY` no .env.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


OK = "✅"
FAIL = "❌"
WARN = "⚠️ "


def _print(status: str, msg: str) -> None:
    print(f"{status}  {msg}")


PLACEHOLDERS = (
    "your_",
    "sk-ant-xxx",
    "AIzaSyXXX",
    "gsk_xxx",
    "seu_",
    "qualquer_string",
)


async def check_env() -> bool:
    try:
        from app.config import settings  # noqa: WPS433
    except Exception as exc:  # noqa: BLE001
        _print(FAIL, f"falha ao carregar settings: {exc}")
        return False

    # Chave do provider ativo é obrigatória; a outra pode ficar placeholder
    if settings.ai_primary == "gemini":
        provider_key = ("GEMINI_API_KEY", settings.gemini_api_key)
    elif settings.ai_primary == "groq":
        provider_key = ("GROQ_API_KEY", settings.groq_api_key)
    else:
        _print(FAIL, f"AI_PRIMARY '{settings.ai_primary}' não suportado")
        return False

    required = [
        ("WA_TOKEN", settings.wa_token),
        ("WA_PHONE_ID", settings.wa_phone_id),
        ("WA_VERIFY_TOKEN", settings.wa_verify_token),
        ("WA_APP_SECRET", settings.wa_app_secret),
        provider_key,
        ("LUCIANA_PHONE", settings.luciana_phone),
    ]
    all_ok = True
    for name, value in required:
        if not value or value.startswith(PLACEHOLDERS):
            _print(FAIL, f"{name} não preenchida (placeholder ou vazia)")
            all_ok = False
        else:
            _print(OK, f"{name} preenchida")
    return all_ok


async def check_redis() -> bool:
    try:
        from app.session import close_redis, get_redis

        client = get_redis()
        pong = await client.ping()
        await close_redis()
        if pong:
            _print(OK, "Redis respondeu ao ping")
            return True
        _print(FAIL, "Redis não respondeu PONG")
        return False
    except Exception as exc:  # noqa: BLE001
        _print(FAIL, f"Redis indisponível: {exc}")
        return False


async def check_postgres() -> bool:
    try:
        from sqlalchemy import text

        from app.database import dispose_engine, get_engine

        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        await dispose_engine()
        _print(OK, "PostgreSQL respondeu SELECT 1")
        return True
    except Exception as exc:  # noqa: BLE001
        _print(FAIL, f"PostgreSQL indisponível: {exc}")
        return False


async def check_prompt() -> bool:
    path = PROJECT_ROOT / "app" / "prompts" / "malu_v4.md"
    if not path.exists():
        _print(FAIL, f"system prompt ausente: {path}")
        return False
    size = path.stat().st_size
    if size < 1000:
        _print(WARN, f"prompt parece pequeno demais ({size} bytes)")
        return False
    _print(OK, f"system prompt presente ({size:,} bytes)")
    return True


async def check_ai() -> bool:
    """Pinga o provider ativo via a função real `ask_malu` (mesma usada em prod)."""
    try:
        from app.ai import active_model_name, ask_malu
        from app.config import settings

        text = await ask_malu([{"role": "user", "content": "diga apenas: ok"}])
        if text:
            _print(
                OK,
                f"{settings.ai_primary.capitalize()} respondeu "
                f"({active_model_name()})",
            )
            return True
        _print(FAIL, f"{settings.ai_primary} retornou resposta vazia")
        return False
    except Exception as exc:  # noqa: BLE001
        _print(FAIL, f"Provider de IA falhou: {exc}")
        return False


async def main() -> int:
    print("🔍 Malu — checagem de ambiente\n")

    results = {
        "env": await check_env(),
        "prompt": await check_prompt(),
        "redis": await check_redis(),
        "postgres": await check_postgres(),
        "ai": await check_ai(),
    }

    print("\n" + "─" * 50)
    all_ok = all(results.values())
    if all_ok:
        print("✅  tudo certo, pode iniciar com `uvicorn app.main:app --reload`")
        return 0
    print("❌  alguma checagem falhou — veja acima")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

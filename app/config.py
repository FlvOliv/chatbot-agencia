"""Configuração centralizada via Pydantic Settings.

Lê variáveis do `.env`. Nunca usar `os.getenv()` em módulos de negócio —
sempre importar `settings` daqui.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações da aplicação carregadas do `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Meta WhatsApp Cloud API
    wa_token: str = Field(..., description="Permanent access token Meta")
    wa_phone_id: str = Field(..., description="Phone number ID Meta")
    wa_verify_token: str = Field(..., description="Verify token do webhook")
    wa_app_secret: str = Field(..., description="App secret Meta — usado no HMAC")

    # Google Gemini (provider primário atual)
    gemini_api_key: str = Field(default="", description="API key Gemini (aistudio.google.com)")
    gemini_model: str = Field(default="gemini-2.5-flash")

    # Groq (stand-by — ativar trocando AI_PRIMARY=groq no .env)
    groq_api_key: str = Field(default="", description="API key Groq (console.groq.com)")
    groq_model: str = Field(default="llama-3.3-70b-versatile")

    # Banco e cache
    database_url: str = Field(
        default="postgresql+asyncpg://malu:malu@localhost:5432/malu"
    )
    redis_url: str = Field(default="redis://localhost:6379/0")

    # Negócio
    luciana_phone: str = Field(..., description="Telefone Lu (E.164 sem +)")
    business_hours_start: int = Field(default=9)
    business_hours_end: int = Field(default=18)

    # IA
    ai_primary: Literal["gemini", "groq", "claude", "openai", "gemma"] = Field(default="gemini")
    ai_fallback: Literal["gemini", "groq", "auto", "none"] = Field(default="none")
    ollama_url: str = Field(default="http://localhost:11434")
    ollama_model: str = Field(default="gemma3")

    # App
    app_env: Literal["development", "staging", "production"] = Field(default="development")
    log_level: str = Field(default="INFO")
    session_ttl_seconds: int = Field(default=86400)

    # CRM API (consumida pelo frontend Next.js)
    crm_api_key: str = Field(
        default="",
        description="API key compartilhada — header X-API-Key nas rotas /api/*",
    )
    crm_cors_origins: str = Field(
        default="http://localhost:3000",
        description="Origens permitidas no CORS, separadas por vírgula",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retorna instância única de Settings (cached)."""
    return Settings()  # type: ignore[call-arg]


settings = get_settings()

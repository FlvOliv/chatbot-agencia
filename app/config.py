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
    # Transcrição de áudio (Whisper da Groq — MESMA chave do chat, mas cota de
    # ASR separada: um 429 nos modelos de texto normalmente NÃO afeta o Whisper).
    # Desligada por padrão: ligar só após teste ao vivo. Desligada (ou em erro),
    # áudio segue o handoff de hoje (acolhe e passa pra Lu).
    audio_transcription_enabled: bool = Field(default=False)
    groq_whisper_model: str = Field(default="whisper-large-v3-turbo")
    # Reserva REAL dentro do próprio Groq: modelo menor/rápido com limites
    # separados. Entra quando o modelo principal falha/é limitado (429), ANTES
    # de cair pro Gemini (que no free vive esgotado). "" desliga.
    groq_fallback_model: str = Field(default="llama-3.1-8b-instant")

    # Cerebras (perna GRÁTIS extra — OpenAI-compatible). Entra DEPOIS do Groq e
    # ANTES do piso pago. NÃO ativar billing/PAYG: usar só o tier grátis. ""
    # (sem chave) = perna pulada. Não treina com dados → seguro p/ PII (LGPD).
    cerebras_api_key: str = Field(default="", description="API key Cerebras (cloud.cerebras.ai)")
    # Modelo grátis da conta da Lu (a conta NÃO tem Llama; confirmar em
    # GET /v1/models). Alternativa disponível hoje: "zai-glm-4.7".
    cerebras_model: str = Field(default="gpt-oss-120b")
    cerebras_base_url: str = Field(default="https://api.cerebras.ai/v1")

    # Mistral = PISO PAGO (OpenAI-compatible). Última rede ANTES do Gemini.
    # Barato, infra UE/LGPD-friendly, não treina com dados no plano pago.
    # Quase nunca é tocado (o buffer grátis Groq+Cerebras cobre o dia a dia).
    mistral_api_key: str = Field(default="", description="API key Mistral (console.mistral.ai)")
    mistral_base_url: str = Field(default="https://api.mistral.ai/v1")
    # Piso pago — provider/modelo e liga/desliga. paid_floor_enabled=false
    # remove o Mistral da cadeia (kill switch). Provider fixo em "mistral" hoje.
    paid_floor_provider: str = Field(default="mistral")
    paid_floor_model: str = Field(default="open-mistral-nemo")
    paid_floor_enabled: bool = Field(default=True)
    # Trava de orçamento: teto de tokens pagos POR MÊS. Atingido o teto, o
    # Mistral é PULADO (segue pro Gemini/erro). <=0 = sem teto (não bloqueia);
    # o liga/desliga real é o paid_floor_enabled.
    monthly_paid_token_cap: int = Field(default=30_000_000)

    # Banco e cache
    database_url: str = Field(
        default="postgresql+asyncpg://malu:malu@localhost:5432/malu"
    )
    redis_url: str = Field(default="redis://localhost:6379/0")

    # Supabase Storage — guarda os áudios dos clientes pra Lu ouvir no painel.
    # Bucket PRIVADO + URL ASSINADA (temporária) → LGPD-friendly. Sem URL/chave,
    # o upload é pulado (a transcrição segue funcionando, só não guarda o áudio).
    supabase_url: str = Field(default="", description="https://<projeto>.supabase.co")
    supabase_service_key: str = Field(
        default="", description="service_role key (upload no Storage; NUNCA expor no front)"
    )
    supabase_audio_bucket: str = Field(default="audios")
    # Validade do link assinado do áudio no painel (segundos). 3600 = 1h.
    audio_url_ttl: int = Field(default=3600)

    # Negócio
    luciana_phone: str = Field(..., description="Telefone Lu (E.164 sem +)")
    business_hours_start: int = Field(default=9)
    business_hours_end: int = Field(default=18)
    panel_base_url: str = Field(
        default="http://localhost:3000",
        description="URL pública do painel CRM — usada no link dos avisos pra Lu",
    )

    # IA
    ai_primary: Literal["gemini", "groq", "claude", "openai", "gemma"] = Field(default="gemini")
    ai_fallback: Literal["gemini", "groq", "auto", "none"] = Field(default="none")
    ollama_url: str = Field(default="http://localhost:11434")
    ollama_model: str = Field(default="gemma3")

    # App
    app_env: Literal["development", "staging", "production"] = Field(default="development")
    log_level: str = Field(default="INFO")
    session_ttl_seconds: int = Field(default=86400)
    # Debounce de rajada (Fase 1C): segundos que a Malu espera juntando
    # mensagens picadas antes de chamar a IA. 0 = desliga (responde na hora).
    debounce_seconds: float = Field(default=7.0)

    # Callbacks (follow-ups). O de 30 min dispara sempre; o pré-24h respeita
    # o horário de silêncio e um buffer antes de fechar a janela de 24h da Meta.
    callback_timezone: str = Field(
        default="America/Sao_Paulo",
        description="Fuso usado pra calcular silêncio e janela do callback pré-24h",
    )
    quiet_start: int = Field(default=20, description="Hora (0-23) que começa o silêncio")
    quiet_end: int = Field(default=8, description="Hora (0-23) que termina o silêncio")
    pre24h_buffer_minutes: int = Field(
        default=60,
        description="Minutos antes do fim da janela de 24h pra disparar o pré-24h",
    )

    # Cron dos follow-ups (substitui o worker Celery): um cron externo bate em
    # POST /internal/tick com este segredo no header X-Cron-Secret. Vazio =
    # endpoint bloqueado (fail-safe). O resumo diário roda 1×/dia a partir desta hora.
    cron_secret: str = Field(default="")
    daily_report_hour: int = Field(
        default=8, description="Hora (0-23, fuso callback_timezone) do resumo diário"
    )

    # Push web (Fase 3): chaves VAPID pra notificar a Lu no navegador.
    # Se vazias, o push fica desligado (não quebra nada). Geradas com py_vapid.
    vapid_public_key: str = Field(default="")
    vapid_private_key: str = Field(default="")
    vapid_subject: str = Field(default="mailto:contato@lumilhas.com")

    # Multi-tenant (Fase 1): chave Fernet pra cifrar segredos por agência
    # (ex.: wa_token na tabela `agencias`). Gerar com:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # Vazia = encrypt/decrypt falham explícito (fail-closed) — nunca segredo em texto puro.
    tenant_secret_key: str = Field(default="", description="Fernet key base64 (32B) p/ segredos por tenant")

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

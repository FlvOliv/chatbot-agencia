"""DTOs (Pydantic) das rotas /api/*.

Separados dos models SQLAlchemy de propósito — controla EXATAMENTE o que
sai pra fora. Mudança no banco não vaza pro frontend sem ajuste explícito.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

# IDs no banco são UUID; o Pydantic v2 não coage UUID->str sozinho.
# Este tipo garante que qualquer id vire string na serialização.
StrId = Annotated[str, BeforeValidator(lambda v: str(v))]


# ---------------------------------------------------------------------------
# Cliente
# ---------------------------------------------------------------------------
class ClienteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    phone: str
    profile_name: str | None = None
    name: str | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Lead
# ---------------------------------------------------------------------------
class LeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: StrId
    phone: str
    name: str | None = None
    destination: str | None = None
    travel_type: str | None = None
    lead_temp: str | None = None
    briefing_md: str | None = None
    created_at: datetime
    updated_at: datetime


class LeadListItem(BaseModel):
    """Versão enxuta — usada na tabela de leads, sem o briefing inteiro."""
    model_config = ConfigDict(from_attributes=True)
    id: StrId
    phone: str
    name: str | None = None
    destination: str | None = None
    lead_temp: str | None = None
    created_at: datetime


class LeadListResponse(BaseModel):
    items: list[LeadListItem]
    total: int
    page: int
    page_size: int


class LeadDetail(BaseModel):
    """Detalhe completo de um lead — usado em /leads/[id]."""
    lead: LeadOut
    cliente: ClienteOut | None = None
    conversation_count: int = 0


# ---------------------------------------------------------------------------
# Conversation
# ---------------------------------------------------------------------------
class MessageOut(BaseModel):
    # protected_namespaces=() pra permitir o campo `model_used` (que conflitaria
    # com o prefixo reservado `model_*` do Pydantic v2)
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
    id: StrId
    phone: str
    role: str
    content: str
    model_used: str | None = None
    created_at: datetime


class ConversationSummary(BaseModel):
    """Resumo por phone — usado na lista de conversas."""
    phone: str
    customer_name: str | None = None
    last_message_at: datetime
    last_message_preview: str
    message_count: int
    lead_temp: str | None = None


class ConversationDetail(BaseModel):
    phone: str
    customer_name: str | None = None
    messages: list[MessageOut]


# ---------------------------------------------------------------------------
# Reserva
# ---------------------------------------------------------------------------
class ReservaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: StrId
    phone: str
    codigo_reserva: str | None = None
    destino: str | None = None
    data_viagem: date | None = None
    status: str
    observacoes: str | None = None
    created_at: datetime


class ReservaCreate(BaseModel):
    phone: str = Field(..., description="Telefone do cliente (deve existir em clientes)")
    codigo_reserva: str | None = None
    destino: str | None = None
    data_viagem: date | None = None
    status: str = Field(default="ativa", pattern="^(ativa|encerrada|cancelada)$")
    observacoes: str | None = None


# ---------------------------------------------------------------------------
# Métricas
# ---------------------------------------------------------------------------
class DashboardMetrics(BaseModel):
    leads_today: int
    leads_week: int
    active_conversations: int
    pending_for_lu: int
    reservas_ativas: int
    by_temperature: dict[str, int]  # {"frio": N, "morno": N, "quente": N, "urgente": N}


# ---------------------------------------------------------------------------
# Insights — séries temporais e agregados para o Painel de Insights
# ---------------------------------------------------------------------------
class DailyCount(BaseModel):
    """Contagem de eventos em um único dia (ISO YYYY-MM-DD)."""
    date: date
    count: int


class TopDestination(BaseModel):
    destination: str
    count: int
    pct: float  # 0..1 — fatia em relação ao total dos top N


class HourlyBucket(BaseModel):
    hour: int = Field(ge=0, le=23)
    count: int


class ConversionRate(BaseModel):
    conversations_started: int
    leads_generated: int
    rate: float  # 0..1


class DashboardInsights(BaseModel):
    range_days: int
    generated_at: datetime
    conversations_per_day: list[DailyCount]
    leads_per_day: list[DailyCount]
    top_destinations: list[TopDestination]
    hourly_distribution: list[HourlyBucket]
    conversion_rate: ConversionRate
    ai_provider_breakdown: dict[str, int]  # {"gemini": N, "groq": N, "unknown": N}

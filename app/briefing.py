"""Extração de briefing + notificação para Lu.

A Malu encerra a coleta gerando um bloco markdown iniciando por
`## Resumo da Solicitação`. Este módulo isola o bloco, classifica a
temperatura do lead e persiste no Postgres.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import settings
from app.models import Lead
from app.whatsapp import send_message

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# O prompt usa "## Resumo da Solicitação de Cotação" — captura também variantes
# do mesmo cabeçalho (caso o modelo gere "## Resumo da Solicitação ...").
_BRIEFING_HEADER_RE = re.compile(
    r"(##\s*Resumo da Solicitação[^\n]*\n.*)",
    re.DOTALL | re.IGNORECASE,
)

# Temperatura aparece como:  **Temperatura do lead:** Quente
_TEMP_RE = re.compile(
    r"\*\*Temperatura do lead:\*\*\s*([^\n*]+)",
    re.IGNORECASE,
)

# WhatsApp do cliente aparece como:  **WhatsApp:** 5511999999999
# Pode estar na mesma linha ou em linha logo abaixo do rótulo.
_WHATSAPP_RE = re.compile(
    r"\*\*WhatsApp:\*\*[ \t]*\n?[ \t]*([^\n*]+)",
    re.IGNORECASE,
)

# Nome do cliente no briefing: **Nome do cliente:** Maria Silva
_NAME_RE = re.compile(
    r"\*\*Nome do cliente:\*\*[ \t]*\n?[ \t]*([^\n*]+)",
    re.IGNORECASE,
)

# Valores que não devem ser tratados como nome real (placeholders da IA)
_NAME_PLACEHOLDERS = {
    "",
    "n/a",
    "n/d",
    "não informado",
    "nao informado",
    "[aguardando você me informar]",
    "[aguardando informacao]",
    "[a confirmar]",
    "—",
    "-",
}

_VALID_TEMPS = {"frio", "morno", "quente", "urgente"}


def extract_briefing(text: str) -> str | None:
    """Retorna o bloco do briefing se presente, senão None."""
    if not text:
        return None
    match = _BRIEFING_HEADER_RE.search(text)
    if not match:
        return None
    return match.group(1).strip()


def parse_lead_temp(briefing: str) -> str:
    """Extrai a temperatura do lead do briefing.

    Aceita variantes ("morno para quente" → "morno"). Default: "morno".
    """
    if not briefing:
        return "morno"
    m = _TEMP_RE.search(briefing)
    if not m:
        return "morno"
    raw = m.group(1).strip().lower()
    # Pega a primeira palavra válida encontrada
    for word in re.findall(r"\w+", raw):
        if word in _VALID_TEMPS:
            return word
    return "morno"


def extract_customer_name(briefing: str) -> str | None:
    """Extrai o nome do cliente do briefing.

    Retorna None se o campo estiver ausente ou for um placeholder
    (ex.: "[Aguardando você me informar]").
    """
    if not briefing:
        return None
    m = _NAME_RE.search(briefing)
    if not m:
        return None
    raw = m.group(1).strip()
    if raw.lower() in _NAME_PLACEHOLDERS:
        return None
    return raw or None


def parse_customer_whatsapp(briefing: str) -> str | None:
    """Extrai o número de WhatsApp do cliente do briefing.

    Retorna None se o campo estiver ausente ou vazio.
    Não normaliza o formato — devolve o que o cliente informou.
    """
    if not briefing:
        return None
    m = _WHATSAPP_RE.search(briefing)
    if not m:
        return None
    raw = m.group(1).strip()
    return raw or None


def _format_phone_display(phone: str) -> str:
    """Formata `5511987654321` → `+55 11 98765-4321` (best effort)."""
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 13 and digits.startswith("55"):
        return f"+{digits[:2]} {digits[2:4]} {digits[4:9]}-{digits[9:]}"
    if len(digits) == 12 and digits.startswith("55"):
        return f"+{digits[:2]} {digits[2:4]} {digits[4:8]}-{digits[8:]}"
    return f"+{digits}" if digits else phone


async def notify_luciana(briefing: str, customer_phone: str) -> bool:
    """Envia mensagem formatada para Lu com o briefing do lead."""
    temp = parse_lead_temp(briefing).capitalize()
    display = _format_phone_display(customer_phone)

    body = (
        f"📋 *Novo lead — Malu*\n\n"
        f"📱 Cliente: {display}\n"
        f"🌡 Temperatura: {temp}\n\n"
        f"{briefing}"
    )

    ok = await send_message(settings.luciana_phone, body)
    if not ok:
        logger.error("falha ao notificar Lu sobre lead %s", customer_phone)
    return ok


async def notify_luciana_returning_client(
    customer_phone: str,
    customer_name: str | None,
) -> bool:
    """Alerta a Lu de que um cliente com reserva existente quer atendimento.

    Diferente do `notify_luciana` (lead novo), esta mensagem sinaliza que a
    Malu transferiu a conversa sem chamar IA — Lu precisa assumir manualmente.
    """
    display = _format_phone_display(customer_phone)
    name_part = f"*{customer_name}*" if customer_name else "Um cliente"

    body = (
        f"🔔 *Cliente com reserva quer atendimento*\n\n"
        f"📱 {display}\n"
        f"👤 {name_part}\n\n"
        f"A Malu transferiu a conversa pra você. Quando puder, "
        f"assume direto pelo WhatsApp."
    )

    ok = await send_message(settings.luciana_phone, body)
    if not ok:
        logger.error(
            "falha ao notificar Lu sobre cliente retornante %s", customer_phone
        )
    return ok


async def save_lead(
    phone: str,
    briefing: str,
    lead_temp: str,
    db: AsyncSession,
) -> Lead:
    """Salva (ou atualiza) o lead no Postgres via UPSERT por phone."""
    stmt = (
        pg_insert(Lead)
        .values(
            phone=phone,
            briefing_md=briefing,
            lead_temp=lead_temp,
        )
        .on_conflict_do_update(
            index_elements=["phone"],
            set_={
                "briefing_md": briefing,
                "lead_temp": lead_temp,
            },
        )
        .returning(Lead.id)
    )
    result = await db.execute(stmt)
    lead_id = result.scalar_one()
    await db.flush()

    fetched = await db.execute(select(Lead).where(Lead.id == lead_id))
    return fetched.scalar_one()

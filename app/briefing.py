"""Extração de briefing + notificação para Lu.

A Malu encerra a coleta gerando um bloco markdown iniciando por
`## Resumo da Solicitação`. Este módulo isola o bloco, classifica a
temperatura do lead e persiste no Postgres.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

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

# Sinal INTERNO de transferência pra Lu (cliente quer falar de uma cotação/reserva
# que a Lu já fez). A Malu escreve "## TRANSFERIR" na última linha — o código
# detecta, transfere a conversa e o marcador NUNCA vai pro cliente.
_TRANSFER_RE = re.compile(r"##\s*TRANSFERIR\b", re.IGNORECASE)

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


# ---------------------------------------------------------------------------
# Briefing ESTRUTURADO (substitui o "garimpo" por regex)
# ---------------------------------------------------------------------------
# Fonte única da verdade dos campos do briefing, na ordem em que aparecem pra
# Lu. A MESMA lista alimenta (a) o schema da extração em JSON (app/ai.py) e
# (b) a renderização do texto pra Lu. Adicionar/remover campo = mexer só aqui.
#   (chave_json, rótulo exibido)
BRIEFING_FIELDS: list[tuple[str, str]] = [
    ("nome_cliente", "Nome do cliente"),
    ("whatsapp", "WhatsApp"),
    ("tipo_atendimento", "Tipo de atendimento"),
    ("origem", "Origem"),
    ("aeroporto_preferencia", "Aeroporto de preferência"),
    ("destino", "Destino"),
    ("data_ida", "Data de ida"),
    ("data_volta", "Data de volta"),
    ("flexibilidade_datas", "Flexibilidade de datas"),
    ("qtd_adultos", "Quantidade de adultos"),
    ("qtd_criancas", "Quantidade de crianças"),
    ("idades_criancas", "Idades das crianças"),
    ("hospedagem_incluida", "Hospedagem incluída?"),
    ("regiao_hospedagem", "Região desejada da hospedagem"),
    ("tipo_hospedagem", "Tipo de hospedagem"),
    ("qtd_quartos", "Quantidade de quartos"),
    ("carro_alugado", "Carro alugado?"),
    ("bagagem_despachada", "Bagagem despachada?"),
    ("preferencia_voo", "Preferência de voo"),
    ("forma_pagamento", "Forma de pagamento"),
    ("orcamento", "Orçamento aproximado"),
    ("motivo_viagem", "Motivo da viagem"),
    ("prazo_decisao", "Prazo de decisão"),
    ("veio_indicacao", "Veio de indicação?"),
    ("ja_viajou", "Já viajou com a Lu Milhas?"),
    ("pendencias", "Pendências para confirmar"),
    ("observacoes", "Observações importantes"),
]

# Campo que a IA CLASSIFICA (não é dado dito pelo cliente)
TEMPERATURA_KEY = "temperatura_lead"

NAO_INFORMADO = "Não informado"


def _clean_value(value: object) -> str | None:
    """Normaliza um valor extraído: None / '' / placeholder → None."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in _NAME_PLACEHOLDERS:
        return None
    return text


def normalize_temp(value: object) -> str:
    """Garante uma temperatura válida (default 'morno')."""
    raw = str(value or "").strip().lower()
    for word in re.findall(r"\w+", raw):
        if word in _VALID_TEMPS:
            return word
    return "morno"


# ---------------------------------------------------------------------------
# Normalização de tipo (P1) — datas e quantidades NUNCA podem virar texto livre
# ---------------------------------------------------------------------------
# Campos que devem sair estruturados; não-coercível = "pendente" (a Malu
# confirma antes de fechar — Regra Inquebrável 4).
_DATE_FIELDS = ("data_ida", "data_volta")
_INT_FIELDS = ("qtd_adultos", "qtd_criancas", "qtd_quartos")
_AGES_FIELD = "idades_criancas"

# Data concreta = dia+mês numéricos (12/11, 12-11-2026) OU "12 de novembro".
_DATE_CONCRETE_RE = re.compile(
    r"\b\d{1,2}[/\-.]\d{1,2}(?:[/\-.]\d{2,4})?\b"
    r"|\b\d{1,2}\s+de\s+[^\W\d_]+",
    re.IGNORECASE,
)

# Números por extenso comuns (até 12 cobre passageiros/quartos com folga).
_NUM_WORDS = {
    "zero": 0, "nenhum": 0, "nenhuma": 0, "um": 1, "uma": 1, "dois": 2,
    "duas": 2, "tres": 3, "três": 3, "quatro": 4, "cinco": 5, "seis": 6,
    "sete": 7, "oito": 8, "nove": 9, "dez": 10, "onze": 11, "doze": 12,
}


def _pendente(raw: str) -> str:
    """Marca um valor não resolvido, preservando o que o cliente disse."""
    return f'pendente (cliente disse: "{raw}")'


def _coerce_int(raw: str) -> int | None:
    """Extrai um inteiro de '2', '2 adultos', 'duas'... ou None se não der."""
    m = re.search(r"\d+", raw)
    if m:
        return int(m.group())
    for word, n in _NUM_WORDS.items():
        if re.search(rf"\b{word}\b", raw, re.IGNORECASE):
            return n
    return None


def normalize_lead_data(data: dict) -> dict:
    """Coage datas/quantidades a tipos concretos antes de salvar/exibir.

    Data relativa/vaga ("Novembro, perto do feriado") ou quantidade não
    numérica vira `pendente` (preservando o texto do cliente) — nunca texto
    solto no briefing. Campo nulo continua nulo (→ "Não informado").
    """
    out = dict(data)
    for field in _DATE_FIELDS:
        raw = _clean_value(out.get(field))
        if raw is None:
            continue
        out[field] = raw if _DATE_CONCRETE_RE.search(raw) else _pendente(raw)
    for field in _INT_FIELDS:
        raw = _clean_value(out.get(field))
        if raw is None:
            continue
        n = _coerce_int(raw)
        out[field] = str(n) if n is not None else _pendente(raw)
    raw_ages = _clean_value(out.get(_AGES_FIELD))
    if raw_ages is not None:
        ages = re.findall(r"\d+", raw_ages)
        out[_AGES_FIELD] = ", ".join(ages) if ages else _pendente(raw_ages)
    return out


def render_briefing(data: dict, customer_phone: str | None = None) -> str:
    """Monta o markdown do briefing pra Lu a partir dos dados ESTRUTURADOS.

    Campo ausente/null vira "Não informado" — nunca um chute. Esta é a fonte
    confiável que a Lu recebe (não o texto livre da IA).
    """
    lines = ["## Resumo da Solicitação de Cotação", ""]
    for key, label in BRIEFING_FIELDS:
        val = _clean_value(data.get(key))
        # WhatsApp: usa o número real do webhook se a IA não capturou
        if val is None and key == "whatsapp" and customer_phone:
            val = customer_phone
        lines.append(f"**{label}:** {val if val is not None else NAO_INFORMADO}")
    temp = normalize_temp(data.get(TEMPERATURA_KEY))
    lines.append(f"**Temperatura do lead:** {temp.capitalize()}")
    return "\n".join(lines)


def lead_columns_from_data(data: dict) -> dict:
    """Extrai os campos que viram COLUNAS da tabela leads (filtros/gráficos)."""
    return {
        "name": _clean_value(data.get("nome_cliente")),
        "destination": _clean_value(data.get("destino")),
        "travel_type": _clean_value(data.get("tipo_atendimento")),
        "lead_temp": normalize_temp(data.get(TEMPERATURA_KEY)),
    }


def split_reply_and_briefing(reply: str) -> tuple[str, str | None]:
    """Separa o que vai pro CLIENTE do bloco de briefing (sinal de fim de coleta).

    Retorna (texto_pro_cliente, bloco_briefing_ou_None). O bloco em si NÃO vai
    pro cliente — serve só como gatilho de que a coleta terminou.
    """
    if not reply:
        return reply, None
    m = _BRIEFING_HEADER_RE.search(reply)
    if not m:
        return reply, None
    before = reply[: m.start()].strip()
    block = m.group(1).strip()
    # "## Resumo" só com o cabeçalho, SEM os campos abaixo = hiccup do modelo
    # (escreveu o header no meio da frase, sem concluir). NÃO finaliza por isso
    # (evita lead/protocolo espúrio) — devolve só o texto do cliente.
    parts = block.split("\n", 1)
    body = parts[1].strip() if len(parts) > 1 else ""
    if not body:
        return before, None
    return before, block


def split_reply_and_transfer(reply: str) -> tuple[str, bool]:
    """Separa o texto pro cliente do sinal de transferência (`## TRANSFERIR`).

    Retorna (texto_pro_cliente_sem_marcador, quer_transferir). O marcador em si
    NUNCA vai pro cliente — serve só como gatilho de que a Malu quer passar a
    conversa pra Lu (cliente falando de uma cotação/reserva já feita).
    """
    if not reply:
        return reply, False
    if not _TRANSFER_RE.search(reply):
        return reply, False
    cleaned = _TRANSFER_RE.sub("", reply).strip()
    return cleaned, True


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


def _panel_link(customer_phone: str) -> str:
    """Link direto pra conversa do cliente no painel (deep link do aviso)."""
    base = settings.panel_base_url.rstrip("/")
    return f"{base}/conversas/{customer_phone}"


def _format_phone_display(phone: str) -> str:
    """Formata `5511987654321` → `+55 11 98765-4321` (best effort)."""
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 13 and digits.startswith("55"):
        return f"+{digits[:2]} {digits[2:4]} {digits[4:9]}-{digits[9:]}"
    if len(digits) == 12 and digits.startswith("55"):
        return f"+{digits[:2]} {digits[2:4]} {digits[4:8]}-{digits[8:]}"
    return f"+{digits}" if digits else phone


async def notify_luciana(
    briefing: str, customer_phone: str, numero: int | None = None
) -> bool:
    """Envia mensagem formatada para Lu com o briefing do lead."""
    temp = parse_lead_temp(briefing).capitalize()
    display = _format_phone_display(customer_phone)
    titulo = (
        f"📋 *Novo lead #{numero} — Malu*"
        if numero is not None
        else "📋 *Novo lead — Malu*"
    )

    # WhatsApp usa * simples pra negrito; ** (markdown) aparece literal. O
    # briefing é gerado em markdown (pro painel) → converte aqui pro envio à Lu.
    briefing_wpp = briefing.replace("**", "*")
    body = (
        f"{titulo}\n\n"
        f"📱 Cliente: {display}\n"
        f"🌡 Temperatura: {temp}\n\n"
        f"{briefing_wpp}\n\n"
        f"👉 Responder no painel: {_panel_link(customer_phone)}"
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
        f"A Malu transferiu a conversa pra você.\n\n"
        f"👉 Responder no painel: {_panel_link(customer_phone)}"
    )

    ok = await send_message(settings.luciana_phone, body)
    if not ok:
        logger.error(
            "falha ao notificar Lu sobre cliente retornante %s", customer_phone
        )
    return ok


async def notify_luciana_ai_down(
    customer_phone: str,
    customer_name: str | None,
) -> bool:
    """Alerta a Lu de que a Malu travou (IA fora do ar) e a conversa foi
    transferida pra ela assumir manualmente no painel.

    Diferente do `notify_luciana_returning_client`: aqui o cliente NÃO pediu
    transferência — foi a IA que caiu (as duas, primária + reserva). A Malu
    avisou o cliente uma vez e silenciou pra não repetir o erro.
    """
    display = _format_phone_display(customer_phone)
    name_part = f"*{customer_name}*" if customer_name else "Um cliente"

    body = (
        f"⚠️ *A Malu travou — assume essa conversa?*\n\n"
        f"📱 {display}\n"
        f"👤 {name_part}\n\n"
        f"A inteligência da Malu ficou indisponível por uns instantes e ela "
        f"passou a conversa pra você pra não deixar o cliente sem resposta.\n\n"
        f"👉 Responder no painel: {_panel_link(customer_phone)}"
    )

    ok = await send_message(settings.luciana_phone, body)
    if not ok:
        logger.error("falha ao notificar Lu sobre Malu travada (%s)", customer_phone)
    return ok


async def notify_luciana_media(
    customer_phone: str,
    customer_name: str | None,
    media_type: str,
) -> bool:
    """Alerta a Lu de que o cliente enviou mídia/documento que a Malu não lê.

    A Malu não tenta transcrever/extrair: acolhe o cliente e passa a conversa
    pra Lu assumir manualmente no painel.
    """
    display = _format_phone_display(customer_phone)
    name_part = f"*{customer_name}*" if customer_name else "Um cliente"

    body = (
        f"📎 *Cliente enviou mídia/documento*\n\n"
        f"📱 {display}\n"
        f"👤 {name_part}\n"
        f"🗂️ Tipo: {media_type}\n\n"
        f"A Malu não lê mídia e passou a conversa pra você.\n\n"
        f"👉 Responder no painel: {_panel_link(customer_phone)}"
    )

    ok = await send_message(settings.luciana_phone, body)
    if not ok:
        logger.error("falha ao notificar Lu sobre mídia do cliente %s", customer_phone)
    return ok


async def save_lead(
    phone: str,
    db: AsyncSession,
    *,
    briefing_md: str,
    lead_temp: str,
    name: str | None = None,
    destination: str | None = None,
    travel_type: str | None = None,
    raw_data: dict | None = None,
) -> Lead:
    """Cria um lead NOVO (uma cotação).

    Cada coleta concluída vira uma cotação separada, com seu próprio `numero` —
    NÃO sobrescreve cotações anteriores do mesmo cliente (a mesma pessoa pode
    pedir várias). Colunas opcionais só entram quando vêm preenchidas.
    """
    values: dict[str, object] = {
        "phone": phone,
        "briefing_md": briefing_md,
        "lead_temp": lead_temp,
    }
    optional = {
        "name": name,
        "destination": destination,
        "travel_type": travel_type,
        "raw_data": raw_data,
    }
    for col, val in optional.items():
        if val:  # ignora None / "" / {}
            values[col] = val

    lead = Lead(**values)
    db.add(lead)
    await db.flush()
    # Recarrega pra trazer os valores gerados no banco (numero, id, created_at).
    await db.refresh(lead)
    return lead

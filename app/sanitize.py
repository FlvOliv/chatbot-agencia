"""Guards de saída — rede de segurança nas respostas da Malu ao cliente.

Rodam em TODA resposta gerada por IA antes do envio ao WhatsApp,
independentemente do modelo da cadeia (70b → 8b → gemini). O prompt pode
escapar — ainda mais nos modelos de reserva, mais fracos — então estes guards
são a defesa determinística que NÃO depende do modelo.
"""

from __future__ import annotations

import re

# Frase de devolução à Lu — espelha a Regra Inquebrável de preço do prompt.
PRICE_SAFE_REPLY = (
    "Os valores são pesquisados e validados pela Lu, porque as tarifas mudam em "
    "tempo real. Vou organizar seus dados certinho e ela te manda um valor real "
    "e confirmado, sem surpresas. 💛"
)

# Sinais de valor monetário. Conservador de propósito pra não confundir com
# data (12/11), idade (5 anos), quantidade (2 adultos) ou horário (10h).
_PRICE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"R\$\s*\d", re.IGNORECASE),                       # R$ 900 / R$900
    re.compile(r"\d[\d.]*\s*(?:reais|real)\b", re.IGNORECASE),    # 900 reais / 1.500 reais
    re.compile(r"\b\d{1,3}\s*mil\b", re.IGNORECASE),             # 2 mil
    re.compile(
        r"\b(?:um|dois|duas|tr[eê]s|quatro|cinco|seis|sete|oito|nove|dez|"
        r"quinze|vinte|trinta|quarenta|cinquenta)\s+mil\b",
        re.IGNORECASE,
    ),                                                            # dois mil
    re.compile(r"\b\d{1,3}(?:\.\d{3})+(?:,\d{2})?\b"),           # 1.500 / 1.200,00
    re.compile(r"\b\d+,\d{2}\b"),                                 # 900,00
    re.compile(
        r"(?:a partir de|em torno de|por volta de|sai por|fica\s+(?:em|por)|custa)"
        r"\s*R?\$?\s*\d",
        re.IGNORECASE,
    ),                                                            # a partir de 900
)


def price_guard(text: str) -> tuple[str, bool]:
    """Detecta menção a preço/valor numa resposta ao CLIENTE.

    Retorna ``(texto, bloqueado)``. Se achar valor monetário, devolve
    ``PRICE_SAFE_REPLY`` (substitui a mensagem inteira) e ``bloqueado=True`` —
    o chamador deve logar pra auditoria. Quem informa preço é só a Lu (P0).
    """
    if not text:
        return text, False
    for pat in _PRICE_PATTERNS:
        if pat.search(text):
            return PRICE_SAFE_REPLY, True
    return text, False


# ---------------------------------------------------------------------------
# Sanitizer de formatação (P2) — WhatsApp usa * ÚNICO pra negrito, não **
# ---------------------------------------------------------------------------
_HEADING_RE = re.compile(r"(?m)^[ \t]*#{1,6}[ \t]*")  # "## Título" no começo da linha
_BOLD_RUN_RE = re.compile(r"\*{2,}")                   # ** ou *** → *


def sanitize_outgoing(text: str) -> str:
    """Normaliza o markdown da IA pro formato do WhatsApp.

    - `**x**` (ou mais asteriscos) → `*x*` (negrito do WhatsApp é `*` único);
    - remove `#` de cabeçalho markdown (linha começando com #);
    - se sobrar asterisco desbalanceado (contagem ímpar), remove todos —
      negrito quebrado fica pior que sem negrito.

    Os exemplos do próprio prompt usavam `**`, e o modelo copiava; este guard
    pega o que o prompt deixar passar, em qualquer modelo da cadeia.
    """
    if not text:
        return text
    text = _BOLD_RUN_RE.sub("*", text)
    text = _HEADING_RE.sub("", text)
    if text.count("*") % 2 != 0:
        text = text.replace("*", "")
    return text

"""Normalização e métricas do eval da Malu. Funções puras, sem I/O nem API.

Regras de normalização (documentadas também em evals/README.md):
- texto: minúsculas, sem acento, sem pontuação, espaços colapsados.
- texto livre (destino, origem, nome…): acerta se TODOS os tokens do gold
  (fora stopwords) aparecem no extraído. "lisboa" × "Lisboa, Portugal" = acerto.
- inteiro (quantidades): primeiro número do texto, aceitando por extenso até 10.
- data: (dia, mês) e, se os dois lados tiverem, o ano. Aceita dd/mm, dd/mm/aa(aa),
  aaaa-mm-dd e "12 de março".
- idades: conjunto de inteiros.
- sim/não: negação ("não", "sem", "dispensa") vence; senão "sim/com/quer/inclui".
"""

from __future__ import annotations

import math
import re
import statistics
import unicodedata
from typing import Any, Iterable

_STOP = {"de", "da", "do", "das", "dos", "e", "em", "para", "pra", "a", "o", "as", "os"}

_NUM_WORDS = {
    "zero": 0, "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4,
    "cinco": 5, "seis": 6, "sete": 7, "oito": 8, "nove": 9, "dez": 10,
}

_MONTHS = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
    "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}

# Tipo de comparação por campo do briefing (o resto é texto livre).
FIELD_KINDS: dict[str, str] = {
    "qtd_adultos": "int",
    "qtd_criancas": "int",
    "qtd_quartos": "int",
    "data_ida": "date",
    "data_volta": "date",
    "idades_criancas": "ages",
    "hospedagem_incluida": "bool",
    "carro_alugado": "bool",
    "bagagem_despachada": "bool",
}

# Mesmo padrão de vazamento de preço da suíte de conformidade
# (scripts/conformance_probe.py::_PRICE_LEAK_RE).
PRICE_LEAK_RE = re.compile(r"R\$\s*\d|\b\d[\d.,]*\s*(mil|reais)\b", re.IGNORECASE)


# ----------------------------------------------------------- normalização --
def fold(value: Any) -> str:
    """Minúsculas, sem acento, sem pontuação, espaços colapsados."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"[^\w\s/-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokens(value: Any) -> set[str]:
    return {t for t in re.split(r"[\s/-]+", fold(value)) if t and t not in _STOP}


def parse_int(value: Any) -> int | None:
    text = fold(value)
    m = re.search(r"\d+", text)
    if m:
        return int(m.group())
    for word in text.split():
        if word in _NUM_WORDS:
            return _NUM_WORDS[word]
    return None


def parse_date(value: Any) -> tuple[int, int, int | None] | None:
    """(dia, mês, ano|None) ou None se não há data concreta."""
    text = fold(value)
    m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", text)
    if m:
        return int(m.group(3)), int(m.group(2)), int(m.group(1))
    m = re.search(r"\b(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?\b", text)
    if m:
        year = m.group(3)
        y = None if year is None else (int(year) + 2000 if len(year) == 2 else int(year))
        return int(m.group(1)), int(m.group(2)), y
    m = re.search(r"\b(\d{1,2}) de ([a-z]+)(?: de (\d{4}))?", text)
    if m and m.group(2) in _MONTHS:
        y = int(m.group(3)) if m.group(3) else None
        return int(m.group(1)), _MONTHS[m.group(2)], y
    return None


def parse_ages(value: Any) -> set[int]:
    return {int(n) for n in re.findall(r"\d+", fold(value))}


def parse_bool(value: Any) -> bool | None:
    words = set(fold(value).split())
    if words & {"nao", "sem", "dispensa", "dispenso", "nenhum", "nenhuma"}:
        return False
    if words & {"sim", "com", "quer", "quero", "inclui", "incluir", "incluida", "precisa", "preciso"}:
        return True
    return None


def is_empty(value: Any) -> bool:
    text = fold(value)
    return not text or text in {"none", "null", "nao informado"} or text.startswith("pendente")


def field_match(field: str, gold: Any, pred: Any) -> bool:
    """True se o valor extraído (`pred`) bate com o gold do campo."""
    if is_empty(pred):
        return False
    kind = FIELD_KINDS.get(field, "text")
    if kind == "int":
        return parse_int(gold) is not None and parse_int(gold) == parse_int(pred)
    if kind == "date":
        g, p = parse_date(gold), parse_date(pred)
        if g is None or p is None or g[:2] != p[:2]:
            return False
        return g[2] is None or p[2] is None or g[2] == p[2]
    if kind == "ages":
        return bool(parse_ages(gold)) and parse_ages(gold) == parse_ages(pred)
    if kind == "bool":
        return parse_bool(gold) is not None and parse_bool(gold) == parse_bool(pred)
    gold_tokens = tokens(gold)
    return bool(gold_tokens) and gold_tokens <= tokens(pred)


# -------------------------------------------------------------- por caso --
def score_fields(gold: dict[str, Any], extracted: dict[str, Any] | None) -> dict[str, bool]:
    """Acerto campo a campo. Sem briefing (`extracted` None) = tudo errado."""
    extracted = extracted or {}
    return {f: field_match(f, g, extracted.get(f)) for f, g in gold.items()}


def check_guard(guard: dict[str, Any] | None, replies: list[str], finalized: bool) -> bool | None:
    """Regra objetiva de guardrail do caso. None = caso sem guardrail.

    guard = {"forbid": [regex], "require_any": [regex], "no_finalize": bool,
             "no_price": bool}
    """
    if not guard:
        return None
    text = "\n".join(replies)
    patterns = list(guard.get("forbid", []))
    if guard.get("no_price"):
        if PRICE_LEAK_RE.search(text):
            return False
    for pat in patterns:
        if re.search(pat, text, re.IGNORECASE):
            return False
    require = guard.get("require_any") or []
    if require and not any(re.search(p, text, re.IGNORECASE) for p in require):
        return False
    if guard.get("no_finalize") and finalized:
        return False
    return True


# ------------------------------------------------------------- agregados --
def percentile(values: Iterable[float], q: float) -> float | None:
    """Percentil por interpolação linear (q em 0..100)."""
    data = sorted(values)
    if not data:
        return None
    if len(data) == 1:
        return data[0]
    pos = (len(data) - 1) * q / 100
    lo, hi = math.floor(pos), math.ceil(pos)
    return data[lo] + (data[hi] - data[lo]) * (pos - lo)


def mean(values: Iterable[float]) -> float | None:
    data = list(values)
    return statistics.fmean(data) if data else None


def median(values: Iterable[float]) -> float | None:
    data = list(values)
    return statistics.median(data) if data else None


def stdev(values: Iterable[float]) -> float | None:
    data = list(values)
    return statistics.stdev(data) if len(data) > 1 else None


def call_cost_usd(prompt_tokens: int, output_tokens: int, price: dict[str, Any]) -> float:
    return (prompt_tokens * price["input_per_m"] + output_tokens * price["output_per_m"]) / 1_000_000

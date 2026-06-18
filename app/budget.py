"""Trava de orçamento do PISO PAGO (Mistral) — camada app-side.

Conta no Redis quantos tokens foram gastos **só no piso pago** (Mistral) no
mês corrente. Antes de chamar o Mistral, `route_and_ask` pergunta se o teto
mensal (`MONTHLY_PAID_TOKEN_CAP`) já foi atingido; se sim, PULA o Mistral e
segue a cadeia (→ gemini → erro/Lu). É a 1ª de 2 camadas — a 2ª é o teto de
gasto no próprio console da Mistral (~US$3), que é o backstop financeiro real.

Escolha de design: se o Redis falhar, contamos 0 (teto NÃO atingido) e
deixamos o Mistral responder. O piso pago existe pra CONFIABILIDADE; um soluço
do Redis não deve derrubar a rede de segurança — e o teto do console cobre o
lado financeiro de qualquer jeito.

Mês em UTC: o deslize de ~3h na virada do mês é irrelevante pra um guarda de
custo; UTC mantém a chave determinística (inclusive nos testes).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.config import settings
from app.session import get_redis

logger = logging.getLogger(__name__)

# Chave por mês (YYYY-MM). Expira sozinha ~70 dias depois → não acumula lixo.
_KEY = "malu:paid_tokens:{}"
_TTL_SECONDS = 70 * 24 * 3600


def _month_key(now: datetime | None = None) -> str:
    """Chave Redis do mês corrente (UTC)."""
    now = now or datetime.now(timezone.utc)
    return _KEY.format(now.strftime("%Y-%m"))


async def paid_tokens_used() -> int:
    """Quantos tokens pagos já foram gastos neste mês. 0 se Redis falhar."""
    try:
        raw = await get_redis().get(_month_key())
        return int(raw) if raw else 0
    except Exception:
        logger.exception("budget: falha ao ler tokens pagos do mês — assumindo 0")
        return 0


async def record_paid_tokens(tokens: int) -> None:
    """Soma `tokens` ao contador do mês (chamado após uma resposta do Mistral)."""
    if tokens <= 0:
        return
    try:
        key = _month_key()
        client = get_redis()
        await client.incrby(key, tokens)
        await client.expire(key, _TTL_SECONDS)
    except Exception:
        logger.exception("budget: falha ao contabilizar %s tokens pagos", tokens)


async def paid_floor_cap_reached() -> bool:
    """True se o teto mensal de tokens pagos já foi atingido.

    `MONTHLY_PAID_TOKEN_CAP <= 0` significa "sem teto" (nunca bloqueia) — o
    liga/desliga real do piso pago é o `PAID_FLOOR_ENABLED`.
    """
    cap = settings.monthly_paid_token_cap
    if cap <= 0:
        return False
    return await paid_tokens_used() >= cap

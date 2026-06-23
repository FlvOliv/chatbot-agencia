"""Endpoint do cron — dispara follow-ups vencidos + resumo diário.

Substitui o worker Celery (que cutucava o Redis 24h). Um cron externo grátis
(ex.: cron-job.org) faz `POST /internal/tick` a cada minuto com o header
`X-Cron-Secret`. Cada batida:
  • dispara os lembretes vencidos (run_due_reminders);
  • roda o resumo diário se já passou da hora e ainda não rodou hoje.

Protegido por `CRON_SECRET` (header `X-Cron-Secret`). Sem o segredo
configurado, o endpoint fica bloqueado (fail-safe) — nunca aberto.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.config import settings
from app.reminders import run_due_reminders
from app.reports import maybe_run_daily_report

router = APIRouter(prefix="/internal", tags=["internal"])


async def require_cron_secret(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
) -> None:
    """Valida o header `X-Cron-Secret` contra `CRON_SECRET`. Vazia = bloqueia tudo."""
    expected = settings.cron_secret
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="CRON_SECRET não configurado no servidor",
        )
    if not x_cron_secret or x_cron_secret != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Cron-Secret inválido ou ausente",
        )


@router.post("/tick", dependencies=[Depends(require_cron_secret)])
async def tick() -> dict:
    """Batida do cron: dispara vencidos + resumo diário (quando for a hora)."""
    reminders_result = await run_due_reminders()
    report_result = await maybe_run_daily_report()
    return {"reminders": reminders_result, "daily_report": report_result}

#!/usr/bin/env bash
# Start script do worker Celery (lembretes + relatório diário).
# Roda como serviço SEPARADO em produção (Railway service ou Heroku worker dyno).
set -euo pipefail

LOG_LEVEL_LC="${LOG_LEVEL:-info}"
LOG_LEVEL_LC="${LOG_LEVEL_LC,,}"

echo "→ Subindo Celery worker + beat..."
exec celery -A workers.tasks worker \
    --beat \
    --loglevel="${LOG_LEVEL_LC}" \
    --concurrency="${WORKER_CONCURRENCY:-2}"

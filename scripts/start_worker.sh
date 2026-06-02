#!/usr/bin/env bash
# Start script do worker Celery (lembretes + relatório diário).
# Roda como serviço SEPARADO em produção (Railway service ou Heroku worker dyno).
set -euo pipefail

echo "→ Subindo Celery worker + beat..."
exec celery -A workers.tasks worker \
    --beat \
    --loglevel="${LOG_LEVEL:-info}" \
    --concurrency="${WORKER_CONCURRENCY:-2}"

#!/usr/bin/env bash
# Start script do serviço web (FastAPI + Uvicorn).
# Roda migrations antes de subir o servidor — Railway/Heroku amigável.
set -euo pipefail

echo "→ Aplicando migrations Alembic..."
alembic upgrade head

echo "→ Subindo Uvicorn na porta ${PORT:-8000}..."
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --workers "${WEB_CONCURRENCY:-2}" \
    --access-log \
    --log-level "${LOG_LEVEL:-info}"

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Pacotes do sistema:
#   libpq-dev / build-essential — asyncpg/SQLAlchemy
#   curl — healthcheck
#   ffmpeg — recodifica as notas de voz do WhatsApp (Opus/OGG c/ duração
#            quebrada) pra MP3 tocável no painel
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev curl ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Instala deps primeiro pra aproveitar cache de camadas do Docker
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Código
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts ./scripts
COPY Procfile ./

# Garante executáveis
RUN chmod +x scripts/start_web.sh

# Usuário não-root
RUN useradd --create-home --shell /bin/bash malu && chown -R malu:malu /app
USER malu

# Railway/Heroku/Render injetam $PORT dinamicamente; default 8000 pra dev local
ENV PORT=8000
EXPOSE 8000

# Healthcheck usa $PORT — funciona local e em qualquer PaaS
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS "http://localhost:${PORT}/health" || exit 1

# Sobe o web (uvicorn + migrations). Os follow-ups rodam por cron externo
# (POST /internal/tick), não mais por worker Celery.
CMD ["./scripts/start_web.sh"]

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Pacotes do sistema (libpq necessária para asyncpg/SQLAlchemy + curl pro healthcheck)
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Instala deps primeiro para aproveitar cache de camadas
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Código
COPY app ./app
COPY workers ./workers
COPY alembic ./alembic
COPY alembic.ini ./

# Usuário não-root
RUN useradd --create-home --shell /bin/bash malu && chown -R malu:malu /app
USER malu

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

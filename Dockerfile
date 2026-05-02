FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# sqlite3 CLI нужен для бэкапов через .backup
RUN apt-get update && apt-get install -y --no-install-recommends \
        sqlite3 \
        tzdata \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .

COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts ./scripts

RUN mkdir -p /app/data /app/data/backups /app/data/logs /app/data/uploads \
    && chmod +x /app/scripts/*.sh

EXPOSE 8080

# Entrypoint сам прогоняет alembic upgrade head перед стартом приложения,
# поэтому после `git pull && docker compose up -d --build` миграции применяются автоматически.
CMD ["/app/scripts/entrypoint.sh"]

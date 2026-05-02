#!/usr/bin/env bash
# Entrypoint контейнера: автоматически накатывает миграции, затем стартует приложение.
# Это нужно чтобы после `git pull` + `docker compose up -d --build` (или просто
# рестарта контейнера) новые миграции применялись без ручного вмешательства.
set -e

echo "[entrypoint] alembic upgrade head"
alembic upgrade head

echo "[entrypoint] starting app"
exec python -m src.main

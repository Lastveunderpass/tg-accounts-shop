#!/usr/bin/env bash
# Восстановление SQLite-базы из бэкапа. Принимает путь к файлу бэкапа.
set -euo pipefail

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <path-to-backup.sqlite3>"
    exit 1
fi

SRC="$1"
DB_PATH="${DB_PATH:-data/db.sqlite3}"

if [ ! -f "$SRC" ]; then
    echo "Backup not found: $SRC"
    exit 1
fi

# на всякий случай — копия текущей БД
if [ -f "$DB_PATH" ]; then
    pre="$DB_PATH.before-restore.$(date -u +%s)"
    cp "$DB_PATH" "$pre"
    echo "Existing DB saved to: $pre"
fi

cp "$SRC" "$DB_PATH"
echo "Restored from: $SRC"
echo "Run: docker compose restart app"

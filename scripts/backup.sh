#!/usr/bin/env bash
# Ручной бэкап SQLite-базы. Запускать внутри контейнера или с настроенным DB_PATH.
set -euo pipefail

DB_PATH="${DB_PATH:-data/db.sqlite3}"
DEST_DIR="${DEST_DIR:-data/backups}"

mkdir -p "$DEST_DIR"

if [ ! -f "$DB_PATH" ]; then
    echo "DB not found: $DB_PATH"
    exit 1
fi

ts=$(date -u +"%Y-%m-%d_%H-%M-%S")
out="$DEST_DIR/db-${ts}.sqlite3"
sqlite3 "$DB_PATH" ".backup '${out}'"
echo "Backup saved: $out"

#!/bin/sh
# BIOTORF backend entrypoint (Docker).
# /data — volume БД. Если реестр клиентов (farms.json) в volume отсутствует,
# кладём стартовый шаблон из образа, чтобы автопривязка по номерам работала
# с первого запуска. Дальше farms.json редактируется админом и переживает
# пересборку контейнера.
set -e

DATA_DIR="${DATA_DIR:-/data}"
FARMS_FILE="${FARMS_FILE:-$DATA_DIR/farms.json}"

if [ ! -f "$FARMS_FILE" ] && [ -f /app/farms.example.json ]; then
  mkdir -p "$DATA_DIR"
  cp /app/farms.example.json "$FARMS_FILE"
  echo "[entrypoint] farms.json не найден — скопирован стартовый шаблон в $FARMS_FILE"
fi

# Команда из docker-compose (например, python telegram_worker.py для tg-worker)
# имеет приоритет; если её нет — стартуем API-сервер uvicorn.
if [ "$#" -gt 0 ]; then
  exec "$@"
fi

exec python -m uvicorn main:app --host 0.0.0.0 --port "${PORT:-8787}"

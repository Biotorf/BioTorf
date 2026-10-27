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
  # tg-worker и прочие одноразовые команды — без супервизора
  if [ "$1" = "python" ] || [ "$1" = "python3" ]; then
    exec "$@"
  fi
fi

# Uvicorn под супервизором: процесс перезапускается после любого падения
# (ОOM, необработанное исключение, рестарт БД), а не уводит контейнер в unhealthy.
while true; do
  python -m uvicorn main:app --host 0.0.0.0 --port "${PORT:-8787}"
  code=$?
  echo "[entrypoint] uvicorn завершился (code=$code) — рестарт через 2с" >&2
  sleep 2
done

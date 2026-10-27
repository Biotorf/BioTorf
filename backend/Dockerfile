# BIOTORF Business OS · backend (FastAPI + PostgreSQL)
FROM python:3.12-slim

# curl нужен для docker healthcheck'а (см. docker-compose.yml);
# ffmpeg — перекодировка записей микрофона в Ogg Opus для голосовых Telegram;
# postgresql-client — pg_dump/psql для резервных копий и миграции данных.
RUN apt-get update && apt-get install -y --no-install-recommends curl ffmpeg postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8787 \
    DB_BACKEND=postgres \
    FARMS_FILE=/data/farms.json \
    MEDIA_DIR=/data/media

EXPOSE 8787

# БД и реестр клиентов живут в /data (volume dbdata в docker-compose) —
# образ stateless, данные переживают пересборку контейнера.
# entrypoint.sh при первом запуске кладёт шаблон farms.json в volume.
RUN chmod +x entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]

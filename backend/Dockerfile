# BIOTORF Business OS · backend (FastAPI + SQLite)
FROM python:3.12-slim

# curl нужен для docker healthcheck'а (см. docker-compose.yml);
# ffmpeg — перекодировка записей микрофона в Ogg Opus для голосовых Telegram
RUN apt-get update && apt-get install -y --no-install-recommends curl ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV DB_PATH=/data/comms.db \
    FARMS_FILE=/data/farms.json \
    PORT=8787

EXPOSE 8787

# БД и реестр клиентов живут в /data (volume dbdata в docker-compose) —
# образ stateless, данные переживают пересборку контейнера.
# entrypoint.sh при первом запуске кладёт шаблон farms.json в volume.
RUN chmod +x entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]

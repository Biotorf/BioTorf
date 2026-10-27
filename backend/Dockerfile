# BIOTORF Business OS · backend (FastAPI + PostgreSQL)
FROM python:3.12-slim

# curl нужен для docker healthcheck'а (см. docker-compose.yml).
# ffmpeg и postgresql-client намеренно НЕ ставим: первый нужен только если
# пользуетесь голосовыми сообщениями в Telegram, второй — только для ручных
# дампов (pg_dump можно выполнить через `docker compose exec postgres pg_dump`).
# Это экономит ~20 минут сборки при --no-cache и ~300 МБ размера образа.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
# psycopg[binary] содержит готовые wheel-пакеты — компиляция из исходников не нужна.
RUN pip install --no-cache-dir --prefer-binary -r requirements.txt

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

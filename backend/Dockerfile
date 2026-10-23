# BIOTORF Business OS · backend (FastAPI + SQLite)
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV DB_PATH=/data/comms.db \
    PORT=8787

EXPOSE 8787

# БД пишет в /data (volume в docker-compose) — образ остаётся stateless.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]

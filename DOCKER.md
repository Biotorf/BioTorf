# BIOTORF Business OS · Docker-стек

Полное окружение в двух контейнерах: **frontend** (Vue 3 + nginx) и **backend**
(FastAPI + SQLite на volume). Тестовые данные коммуникаций из фронтенда удалены —
лента «Коммуникации» теперь живёт только в базе бэкенда.

## Быстрый старт

```bash
cp .env.example .env          # при желании задайте свои секреты интеграций
docker compose up -d --build
```

| Сервис | URL |
|---|---|
| Приложение (фронт + прокси API) | http://localhost:8080 |
| Swagger API | http://localhost:8080/docs или http://localhost:8787/docs |
| Health | http://localhost:8080/health |

Фронтенд во docker-стеке сам определяет адрес API по текущему хосту
(nginx проксирует `/api`, `/webhooks`, `/health` на backend). Если бэкенд
недоступен — приложение деградирует в локальный демо-режим (localStorage).

## Структура

```
docker-compose.yml      # стек: backend + frontend (+ опциональный tg-воркер)
.env.example            # секреты и настройки (скопируйте в .env)
backend/Dockerfile      # python:3.12-slim + uvicorn, БД в /data (volume dbdata)
biotorf-os/Dockerfile   # node:20 build → nginx:alpine, SPA + reverse proxy
biotorf-os/nginx.conf   # маршруты фронта и проксирование API/вебхуков
```

## Данные и база

- SQLite хранится в named-volume `dbdata` (`/data/comms.db`) — переживает
  пересборку образов и перезапуск контейнеров.
- Перезапуск без потери данных: `docker compose up -d`.
- Полная очистка ленты: `docker compose down -v` ⚠ удалит все коммуникации.
- Реестр клиентов для автопривязки по телефону: по умолчанию в контейнер
  монтируется `backend/farms.example.json` (он есть в git — стек стартует
  без дополнительных шагов). Чтобы вести свой реестр:
  `cp backend/farms.example.json backend/farms.json`, отредактируйте его и
  укажите `FARMS_HOST_FILE=./backend/farms.json` в `.env` (или перед запуском:
  `FARMS_HOST_FILE=./backend/farms.json docker compose up -d`).
  Изменения в файле на хосте видны бэкенду сразу.

## Проверка ленты после запуска

**1. Тестовые данные (звонки + TG + WhatsApp) одним запросом:**

```bash
curl -X POST http://localhost:8787/api/dev/seed      # 5 тестовых записей с автопривязкой
curl http://localhost:8787/api/comms                  # что в ленте
curl -X POST http://localhost:8787/api/dev/reset      # очистить ленту
```

После seed откройте http://localhost:8080 → раздел «Коммуникации»: там будут
входящие/исходящие звонки и сообщения, привязанные к клиентам из реестра.

**2. Эмуляция реального вебхука телефонии (как от AТС):**

```bash
# входящий звонок от клиента F-001 (телефон из farms.json):
curl -X POST "http://localhost:8787/webhooks/telephony?token=<TELEPHONY_TOKEN из .env>" \
  -H 'Content-Type: application/json' \
  -d '{"call_id":"t1","direction":"inbound","from":"+996700112233","to":"+996312000000","duration":120,"status":"answered"}'
```

Звонок появится в разделе «Коммуникации» на http://localhost:8080 с автопривязкой к клиенту.

## Telegram-воркер (опционально)

```bash
TELEGRAM_BOT_TOKEN=... docker compose --profile tg up -d telegram-worker
```

## Локальная разработка (без docker)

```bash
cd backend && pip install -r requirements.txt && uvicorn main:app --reload --port 8787
cd biotorf-os && npm install && npm run dev     # http://localhost:5173
```

## Перед боевым использованием

1. Замените dev-секреты в `.env` на длинные случайные строки
   (`openssl rand -hex 24`).
2. Поставьте HTTPS перед nginx (Let's Encrypt / облачный балансировщик) —
   вебхуки Telegram/WhatsApp требуют публичный HTTPS URL.
3. Настройте бэкап volume `dbdata` (SQLite-файл).

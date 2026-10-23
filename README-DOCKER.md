# BIOTORF Business OS · Docker-стек (быстрый старт)

Этот файл — краткая инструкция по запуску всей системы в Docker.
Полное руководство пользователя по интерфейсу — в [README.md](README.md),
подробности интеграций — в [DOCKER.md](DOCKER.md) и [backend/README.md](backend/README.md).

## Что внутри стека

| Сервис | Образ | Назначение |
|---|---|---|
| `frontend` | Vue 3 + nginx (multi-stage build) | SPA + reverse proxy `/api`, `/webhooks`, `/health` на бэкенд |
| `backend` | FastAPI + SQLite (python:3.12-slim) | Лента «Коммуникации»: звонки, Telegram, WhatsApp; вебхуки интеграций |
| `telegram-worker` *(опционально)* | python | Long-poll воркер Telegram Bot API → автоприём сообщений в ленту |

Данные БД переживают перезапуск (volume `dbdata`). Тестовые данные коммуникаций
из фронтенда удалены — лента живёт только в базе бэкенда.

## Запуск (2 команды)

```bash
cp .env.example .env        # при желании задайте свои секреты интеграций
docker compose up -d --build
```

| Адрес | Что откроется |
|---|---|
| http://localhost:8080 | Приложение (раздел «Коммуникации» в меню слева) |
| http://localhost:8080/docs | Swagger REST API |
| http://localhost:8080/health | Проверка работоспособности бэкенда |

## Наполнить ленту тестовыми данными

```bash
curl -X POST http://localhost:8080/api/dev/seed
```

Затем обновите страницу «Коммуникации» — появятся звонки, Telegram- и WhatsApp-сообщения,
автоматически привязанные к клиентам из реестра (по умолчанию `backend/farms.example.json`, свой — через `FARMS_HOST_FILE` в `.env`).

## Эмуляция реальных событий (проверка без телефона)

**Входящий звонок** (имитация CDR от IP-телефонии):

```bash
curl -X POST "http://localhost:8080/webhooks/telephony?token=dev-telephony-token" \
  -H "Content-Type: application/json" \
  -d '{"from":"+996700112233","to":"0312100100","dir":"in","duration":0,"ts":"2026-10-24T10:00:00"}'
```

**Сообщение в Telegram** (имитация вебхука Bot API):

```bash
curl -X POST "http://localhost:8080/webhooks/telegram?secret=dev-telegram-secret" \
  -H "Content-Type: application/json" \
  -d '{"message":{"chat":{"id":111,"phone_number":"+996700112233"},"from":{"first_name":"Тест"},"text":"Здравствуйте, нужна консультация по биопрепаратам"}}'
```

После каждого запроса запись мгновенно появляется в ленте (индикатор
«✅ синхронизируется с сервером» вверху страницы).

## Полезные команды

```bash
docker compose logs -f backend     # логи бэкенда
docker compose down                # остановить (данные сохранятся)
docker compose down -v             # остановить И УДАЛИТЬ базу ⚠
```

## Реальные интеграции (боевой режим)

1. **Телефония** — в панели провайдера (Asterisk / UIS / Манго) укажите HTTP-выгрузку
   CDR на `https://<ваш-домен>/webhooks/telephony?token=<секрет из .env>`.
2. **Telegram** — получите токен бота, пропишите `TELEGRAM_BOT_TOKEN` в `.env`
   и запустите воркер: `docker compose --profile tg-worker up -d telegram-worker`.
3. **WhatsApp Business Cloud API** — в Meta Developers укажите callback URL
   `https://<ваш-домен>/webhooks/whatsapp` и VERIFY_TOKEN / APP_SECRET из `.env`.

Перед боевым запуском замените все dev-секреты в `.env` на случайные длинные строки
и поднимайте стек за HTTPS (reverse proxy / Traefik / Caddy).

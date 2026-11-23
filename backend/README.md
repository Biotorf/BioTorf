# BIOTORF Business OS · backend (сервис коммуникаций) v0.1

Бэкенд для раздела **«Коммуникации»**: общая лента входящих/исходящих звонков,
сообщений Telegram и WhatsApp. Данные — SQLite (`comms.db`), API — FastAPI.

## Запуск (dev)

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env          # заполните секреты интеграций
uvicorn main:app --reload --port 8787
```

Swagger-документация: http://localhost:8787/docs

> **Продактив-запуск — через Docker:** `docker compose up -d --build` в корне
> репозитория (фронт + бэкенд + volume для БД). Подробности — в `DOCKER.md`.
> Путь БД настраивается переменной окружения `DB_PATH` (в контейнере — `/data/comms.db`).

Фронтенд (`biotorf-os/`) сам определяет доступность бэкенда через `/health`:
если он поднят — лента «Коммуникации» синхронизируется с сервером;
если нет — приложение работает как локальное демо на localStorage.

## REST API

| Метод | Путь | Назначение |
|---|---|---|
| GET    | `/api/comms?kind=&farmId=&unreadOnly=&limit=&offset=` | лента с фильтрами |
| POST   | `/api/comms` | зафиксировать коммуникацию вручную |
| PATCH  | `/api/comms/{id}` | обновить (резюме звонка, контакт…) |
| DELETE | `/api/comms/{id}` | удалить запись |
| POST   | `/api/comms/{id}/read` / `/api/comms/read-all` | отметить прочитанным |
| POST   | `/api/comms/{id}/link?farmId=F-001` | привязать к хозяйству |
| GET    | `/api/stats` | счётчики: всего/непрочитанные/пропущенные/без привязки |
| GET    | `/health` | проверка живости |
| POST   | `/api/dev/seed` / `/api/dev/reset` | демо-данные (только для разработки) |

## Вебхуки (автоприём сообщений и звонков)

Для входящих настройте секрет канала в окружении сервера или в настройках CRM,
где это поддерживается. Используйте HTTPS для подключения внешних сервисов.

### 1. IP-телефония → звонки
`POST /webhooks/telephony?token=$TELEPHONY_TOKEN`

Asterisk/UIS/Манго и т. п. шлют CDR (одна запись или массив):

```json
{ "call_id": "…", "direction": "inbound|outbound", "from": "+996…", "to": "+996…",
  "timestamp": "ISO-8601", "duration": 120, "status": "answered|missed",
  "recording_url": "…" }
```

Пропущенные (`missed`, `no-answer`, `busy` или нулевая длительность) помечаются
как «Пропущенный».

### 2. Telegram → сообщения
`POST /webhooks/telegram` принимает заголовок `X-Telegram-Bot-Api-Secret-Token`
для вебхука Bot API и `X-Bot-Secret` для внутреннего воркера.

Telegram требует публичный HTTPS. Для локального запуска используйте воркер
long-polling: создайте бота у @BotFather, затем:

```bash
TELEGRAM_BOT_TOKEN=123:ABC… TELEGRAM_WEBHOOK_SECRET=<секрет> \
python telegram_worker.py [--api http://127.0.0.1:8787]
```

В CRM можно сохранить токен бота и секрет вебхука в разделе «Каналы».
Значения `TELEGRAM_BOT_TOKEN` и `TELEGRAM_WEBHOOK_SECRET` в окружении имеют
приоритет. Клиенту нужно начать личный диалог с ботом до первого ответа.

### 3. WhatsApp Business Cloud API (Meta)
`POST /webhooks/whatsapp` — проверяется подпись `X-Hub-Signature-256`
(секрет = `WHATSAPP_APP_SECRET`). В Meta Developers укажите callback URL этого
сервера и `WHATSAPP_VERIFY_TOKEN` для GET-верификации. Для исходящих подключите
токен и числовой Phone Number ID в CRM или задайте обе переменные
`WHATSAPP_TOKEN` и `WHATSAPP_PHONE_NUMBER_ID`. Обычный ответ доступен в течение
24 часов после входящего сообщения. В другом случае используйте одобренный шаблон
из `WHATSAPP_TEMPLATES_JSON`.

### 4. Другие каналы

`POST /webhooks/channel/{kind}` принимает сообщения внешнего коннектора. Передайте
секрет канала в `X-Webhook-Secret`, идентификатор собеседника в `handle` или
`phone` и идентификатор события в `externalId`. Для отправки настройте
`CHANNEL_OUTBOUND_WEBHOOK_<KIND>` или запустите обработчик очереди и включите
`CHANNEL_OUTBOX_ENABLED_<KIND>=1`. Например, для ВКонтакте суффикс — `VK`.

## Автопривязка к клиентам

Входящая коммуникация сопоставляется с карточками клиентов и контактов по номеру
телефона или Telegram-имени. Поддерживается и прежний снимок реестра
`backend/farms.json`. Если совпадения нет, сохраните клиента из открытого диалога.

## Идемпотентность

Webhook-события хранятся с `external_id` (update_id / wamid / call_id);
повторная доставка того же события не создаёт дубль.

## План развития

- аутентификация сотрудников (JWT) и права, сейчас backend — сетевой слой данных;
- отправка исходящих прямо из ленты (Send API бота / WhatsApp messages API);
- перенос всей CRM-модели (farms, deals, tasks…) на сервер вместо localStorage.

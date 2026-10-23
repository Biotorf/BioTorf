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

Все вебхуки защищены секретами из `.env`; без настройки секрета возвращают 503.

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
`POST /webhooks/telegram` + заголовок `X-Bot-Secret: $TELEGRAM_WEBHOOK_SECRET`

Telegram требует публичный HTTPS. Для локального запуска используйте воркер
long-polling: создайте бота у @BotFather, затем:

```bash
TELEGRAM_BOT_TOKEN=123:ABC… TELEGRAM_WEBHOOK_SECRET=<секрет> \
python telegram_worker.py [--api http://127.0.0.1:8787]
```

Каждое сообщение клиента боту появится в ленте как входящий Telegram-диалог.

### 3. WhatsApp Business Cloud API (Meta)
`POST /webhooks/whatsapp` — проверяется подпись `X-Hub-Signature-256`
(секрет = `WHATSAPP_APP_SECRET`). В Meta Developers укажите callback URL этого
сервера; GET-верификация `hub.verify_token` также поддержана.

## Автопривязка к клиентам

При приёме звонок/сообщение сопоставляется с хозяйством по нормализованному
номеру телефона. Реестр берётся из `backend/farms.json` — snapshot вида
`[{"id":"F-001","name":"…","phone":"+996 …"}]`. Если файла нет или номер
неизвестен — запись попадает в блок «Не определён» для ручной привязки из UI.

## Идемпотентность

Webhook-события хранятся с `external_id` (update_id / wamid / call_id);
повторная доставка того же события не создаёт дубль.

## План развития

- аутентификация сотрудников (JWT) и права, сейчас backend — сетевой слой данных;
- отправка исходящих прямо из ленты (Send API бота / WhatsApp messages API);
- перенос всей CRM-модели (farms, deals, tasks…) на сервер вместо localStorage.

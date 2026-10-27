# Деплой BIOTORF Business OS на OneReza

Проект **не является Docker-совместимым** для OneReza (на платформе нет Docker и
нельзя поднять контейнер PostgreSQL из compose-файла). Правильная схема:

```
OneReza project #1  →  backend  (Python / FastAPI + managed PostgreSQL)
OneReza project #2  →  frontend (Node / Vite → статика biotorf-os/dist)
```

---

## Проект 1 — Backend (FastAPI)

| Поле прессета | Значение |
|---|---|
| Framework / шаблон | **Python → FastAPI** (Uvicorn) |
| Root directory | `backend` |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| Output directory | — (не нужен, сервер динамический) |
| Port | переменная `PORT` (OneReza сам подставляет; не жёстьте 8787) |
| Health check path | `/health` |

### Переменные окружения (Backend)

Обязательные:

| Ключ | Значение |
|---|---|
| `DATABASE_URL` | DSN managed-PostgreSQL от OneReza (`postgresql://user:pass@host:5432/db`) |
| `DB_BACKEND` | `postgres` |
| `AUTH_PASSWORD` | длинный случайный пароль (≥12 симв.) — **без него API отвечает 503** |
| `AUTH_SECRET` | отдельный секрет для подписи JWT (сгенерируйте, например `openssl rand -hex 32`) |
| `CORS_ORIGINS` | `https://<адрес-фронта-onereza>,http://localhost:8080,http://localhost:5173,null` |
| `MEDIA_DIR` | путь в постоянном хранилище проекта (например `/data/media`) |
| `FARMS_FILE` | например `/data/farms.json` |

Интеграции (по факту, иначе каналы просто отключены):

| Ключ | Откуда брать |
|---|---|
| `TELEGRAM_BOT_TOKEN` | @BotFather |
| `TELEGRAM_WEBHOOK_SECRET` | любой длинный случайный строка, сверяется с заголовком Telegram |
| `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_APP_SECRET` | Meta Business / README-WHATSAPP.md |
| `TELEPHONY_TOKEN` | IP-телефония (секрет вебхука CDR) |

⚠ Не включайте `DEV_MODE` в проде.

### Схема БД

При старте бэкенд сам применяет `backend/schema.sql` к PostgreSQL
(startup-хук `_ensure_schema`). Ничего дополнительно мигрировать не нужно.
Перенос старых данных из SQLite — один раз локально:
`python migrate_sqlite_to_pg.py old-comms.db` (при заданном `DATABASE_URL`).

---

## Проект 2 — Frontend (Vue 3 + Vite)

| Поле прессета | Значение |
|---|---|
| Framework / шаблон | **Vite** (или Node.js static / Custom) |
| Root directory | `biotorf-os` |
| Install command | `npm ci` (в репо есть `package-lock.json`) |
| Build command | `npm run build` |
| Output directory | `dist` |
| Server command | оставить пустым (чистая SPA-статика отдаётся CDN/хостингом OneReza) |

### Переменные окружения (Frontend) — это env сборки (префикс `VITE_`)

| Ключ | Значение |
|---|---|
| `VITE_COMMS_API` | публичный URL бэкенда-проекта на OneReza, напр. `https://biotorf-backend.onreza.app` |

Если оставить пустым, фронт будет считать бэкенд своим же origin — на OneReza
фронт и бэк это разные адреса, поэтому **переменную задать обязательно**.

Также убедитесь, что адрес фронта добавлен в `CORS_ORIGINS` бэкенда (см. выше).

---

## Вебхуки (Telegram / WhatsApp / телефония)

После деплоя укажите внешние сервисы на URL **бэкенд-проекта**:

```
POST https://<backend-onereza>/webhooks/telegram
POST https://<backend-onereza>/webhooks/whatsapp
POST https://<backend-onereza>/webhooks/telephony
GET  https://<backend-onereza>/health      ← проверка живости
```

Проверка после деплоя:

```bash
curl -s https://<backend-onereza>/health
# ожидаем JSON {"ok": true, ...} без пути к файлам
```

## Частые ошибки

- **405 на POST /auth/** — значит фронт проксирует запрос в себя же (SPA), а не
  в бэкенд: проверьте `VITE_COMMS_API`.
- **503 на всех /api/** — не задан `AUTH_PASSWORD` на бэкенде.
- **Бэкенд падает на старте** — неверный/недоступный `DATABASE_URL` или база не
  создана в панели OneReza.
- **Голосовые/медиа не работают после рестарта** — `MEDIA_DIR` указывает на
  непостоянный каталог; используйте volume/persistent path платформы.

# 🐳 BIOTORF Business OS в Docker Desktop — пошаговая привязка

Всё приложение (фронтенд + бэкенд + база + опциональный Telegram-воркер) запускается
одной командой и полностью видна в интерфейсе **Docker Desktop**.

---

## 1. Подготовка (один раз)

1. Установите [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows/Mac) и убедитесь, что он запущен (иконка кита в трее — зелёная).
2. Клонируйте репозиторий (или скачайте ZIP и распакуйте):
   ```bash
   git clone https://github.com/Biotorf/BioTorf.git
   cd BioTorf
   ```
3. Создайте файл конфигурации из шаблона:
   - **Mac/Linux:** `cp .env.example .env`
   - **Windows (PowerShell):** `Copy-Item .env.example .env`
   Файл `.env` лежит рядом с `docker-compose.yml`. Для локального тестирования можно ничего не менять — дефолтные значения рабочие.

---

## 2. Запуск

В терминале внутри папки проекта:

```bash
docker compose up -d --build
```

Первый запуск соберёт два образа (может занять 3–5 минут), дальше — секунды.

### Проверка в Docker Desktop
Откройте Docker Desktop → вкладка **Containers**. Появится группа (stack) **`biotorf`** — именно так проект «привязывается» к Desktop:

| Контейнер | Роль | Адрес |
|---|---|---|
| `biotorf-frontend` | Vue 3 приложение за nginx | http://localhost:8080 |
| `biotorf-backend` | FastAPI + SQLite | API на :8787, прокси через :8080 |
| `biotorf-tg-worker` *(опционально)* | Telegram long-poll воркер | — |

Все три контейнера должны быть **зелёные / running**. Клик по контейнеру → логи, кнопка exec → терминал внутрь контейнера.

---

## 3. Альтернатива без терминала — прямо из Docker Desktop

1. Откройте Docker Desktop и перейдите на вкладку **Containers**.
2. Нажмите **+** (или **Workspaces → Add new workspace**) и укажите путь к папке проекта с `docker-compose.yml`.
   Альтернатива: просто откройте эту папку в VS Code с плагином Docker — Desktop подхватит compose-файл автоматически.
3. Desktop распознает compose-файл и покажет карточку стека с кнопкой **▶️ Up** — запуск сборкой и стартом всех сервисов без единой команды.
4. После запуска стек виден на вкладке **Containers → biotorf**, там же кнопки Stop / Restart / Logs / Delete.

---

## 4. Данные и база

- База SQLite живёт в named volume **`dbdata`** (виден в Docker Desktop → **Volumes**). Данные переживают перезапуск и пересборку контейнеров.
- Реестр клиентов для автопривязки по телефонам по умолчанию — `backend/farms.example.json` (в git). Для своего реестра: `cp backend/farms.example.json backend/farms.json`, отредактируйте и добавьте в `.env` строку `FARMS_HOST_FILE=./backend/farms.json`, затем `docker compose up -d`.

Проверить volume:
```bash
docker volume ls | grep dbdata
```

---

## 5. Быстрая проверка, что коммуникации работают

```bash
# 1) наполнить ленту демо-данными
curl -X POST http://localhost:8787/api/dev/seed

# 2) эмулировать входящий звонок с номера клиента
curl -X POST "http://localhost:8787/webhooks/telephony?token=dev-telephony-token" \
  -H "Content-Type: application/json" \
  -d '{"call_id":"test-1","direction":"inbound","from":"+996700112233","to":"+996312555000","status":"answered","duration":95,"timestamp":"2026-10-24T10:00:00Z"}'

# 3) эмулировать сообщение Telegram
curl -X POST "http://localhost:8787/webhooks/telegram?secret=dev-telegram-secret" \
  -H "Content-Type: application/json" \
  -d '{"message":{"message_id":1,"from":{"id":1,"username":"fermer_test"},"chat":{"id":1},"date":1761200000,"text":"Здравствуйте, хочу задать вопрос по биопрепарату"}}'
```

После этого откройте **http://localhost:8080** → раздел **Коммуникации**: записи появятся в общей ленте с автопривязкой к клиенту.

Swagger API: **http://localhost:8080/docs**

---

## 6. Telegram-воркер (когда появится бот)

```bash
# в .env заполните TELEGRAM_BOT_TOKEN=*** токен от @BotFather ──
docker compose --profile tg up -d
```
Контейнер `biotorf-tg-worker` появится в том же стеке в Docker Desktop; сообщения, написанные боту, будут падать в ленту автоматически.

---

## 7. Полезные команды

| Действие | Команда |
|---|---|
| Остановить всё (данные сохранятся) | `docker compose down` |
| Полный сброс ⚠ удалит базу | `docker compose down -v` |
| Пересобрать после изменения кода | `docker compose up -d --build` |
| Логи бэкенда | `docker logs -f biotorf-backend` |
| Статус стека | `docker compose ps` |

В Docker Desktop то же самое делается кнопками: **Stop / Restart / Rebuild / Logs / Purge** на карточке стека `biotorf`.

---

## Частые проблемы

- **Порт занят** (`port is already allocated`): поменяйте внешние порты в `docker-compose.yml` (например, `"8081:80"`).
- **Долгая первая сборка**: это нормально — качаются base-образы python/nginx и ставятся зависимости.
- **Windows + пути**: запускайте команды из PowerShell/CMD в папке проекта; Docker Desktop сам пробрасывает файловую систему через WSL2.
- **Обновили код, но фронт не изменился**: `docker compose up -d --build` пересоберёт образы (nginx-контейнер содержит собранный dist, hot-reload нет).

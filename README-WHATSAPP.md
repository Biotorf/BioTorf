# 📱 WhatsApp Business Cloud API — настройка за 15 минут

Двусторонняя связь с клиентами в WhatsApp прямо из ленты «Коммуникации»:
входящие сообщения попадают в CRM автоматически, ответы отправляются кнопкой
из сайта с вашего бизнес-номера.

```
Клиент (WhatsApp) ⇄ Meta Cloud API ⇄ biotorf-backend ⇄ лента «Коммуникации» на localhost:8080
```

---

## Шаг 1. Аккаунт Meta (5 минут)

1. Зайдите на <https://developers.facebook.com> → **My Apps** → Create App → тип **Business**.
2. В приложении: **Add Product → WhatsApp → Set up**.
3. Привяжите **Meta Business Portfolio** (создайте, если нет).
4. На странице **API Setup** вы увидите:
   - **Phone number ID** — цифры вида `1088…` (это `WHATSAPP_PHONE_NUMBER_ID`);
   - **Access token** — временный токен на 24 часа (потом заменим на постоянный);
   - тестовый номер + поле **«To»** для отправки первого сообщения.

> ⚠️ На тестовом номере Meta пишет только тем получателям, которые добавлены
> в список **Manage test numbers → WABA test numbers** (до 20 номеров). Для
> боевого режима пройдите верификацию бизнеса и подключите свой номер
> (+6 мин, платно после 1000 бесплатных диалогов/мес).

## Шаг 2. Вебхук входящих сообщений

Чтобы входящие долетали до бэкенда, ему нужен **публичный HTTPS URL**.
Варианты:

| Вариант | Когда использовать |
|---|---|
| **cloudflared туннель** | локальная разработка, бесплатно, без сервера |
| VPS с доменом + nginx | боевой режим |

### Быстрый туннель (разработка)

```bash
# отдельное окно терминала:
cloudflared tunnel --url http://localhost:8787
# скопируйте появившийся URL вида https://xxxx.trycloudflare.com
```

### Настройка в Meta (WhatsApp → Configuration)

- **Webhook callback URL:** `https://ВАШ-URL/webhooks/whatsapp`
- **Verify token:** любое длинное значение (например `moj-long-random-token`)
- Нажмите **Verify and save** → бэкенд ответит challenge'ем ✅
- **Webhook fields:** включите подписку на `messages`.

> Verify token из Meta должен совпадать с `WHATSAPP_APP_SECRET` в `.env` —
> именно им Meta подписывает вебхуки (X-Hub-Signature-256), и GET-верификация
> сравнивает его с этим значением.

## Шаг 3. Секреты в .env

```ini
# подпись вебхуков Meta = Verify token из Шага 2
WHATSAPP_APP_SECRET=moj-long-random-token
# исходящая отправка:
WHATSAPP_TOKEN=EAA...           # постоянный System User token (см. ниже)
WHATSAPP_PHONE_NUMBER_ID=108812345678901
```

**Постоянный токен** (временный живёт 24 ч): Business Settings → Users →
**System Users** → Add (+admin role) → Generate token → permissions
`whatsapp_business_messaging`, `whatsapp_business_management` → выбрать WABA.

Перезапустите стек:

```bash
docker compose up -d --force-recreate backend
docker logs biotorf-backend | grep whatsapp
# успех: [whatsapp] конфигурация принята Meta: номер 7 (999) 123-45-67 (id=1088...) — исходящая отправка активна
```

## Шаг 4. Проверка

**Входящие** — напишите с телефона-получателя на ваш бизнес-номер:

```bash
curl "http://localhost:8787/api/comms?kind=whatsapp"   # запись появилась в ленте
```

Или эмуляция вебхука (подпись считать не обязательно на dev-секрете,
используйте /api/dev или просто пришлите payload с правильным HMAC).

**Исходящие** — откройте http://localhost:8080 → «Коммуникации» → входящее
WhatsApp-сообщение → **Ответить**. Над полем ввода должна быть зелёная строка
«✉ Сообщение будет реально отправлено клиенту в WhatsApp с бизнес-номера …».
Статус записи станет «Доставлено» (с wamid в payload) или «Ошибка доставки»
с причиной от Meta (например, получатель вне списка тестовых номеров).

## Частые ошибки Meta

| Код | Причина | Решение |
|---|---|---|
| 131026 | получатель не имеет WhatsApp / не принял шаблон | проверить номер |
| 132000 | вне 24-часового окна диалога | слать approved template |
| 131013 | номер получателя в списке тестовых не найден | добавить в Manage test numbers |
| 190 / 401 | токен истёк | перевыпустить System User token |
| подпись не проходит | WHATSAPP_APP_SECRET ≠ Verify token в Meta | сверить значения |

## Структура файлов

- `backend/whatsapp_client.py` — обёртка Graph API (отправка + проверка конфигурации)
- `backend/main.py` — `/webhooks/whatsapp` (POST приём, GET верификация),
  `POST /api/comms/{id}/send` для kind=whatsapp, `/api/capabilities`
- Фронт показывает баннер «не настроен» с текстом конкретной ошибки Meta.

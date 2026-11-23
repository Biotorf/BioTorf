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

## Шаг 3. Секреты в .env

```ini
WHATSAPP_VERIFY_TOKEN=             # значение Verify token из настройки callback
WHATSAPP_APP_SECRET=               # App Secret из Meta App Settings → Basic
WHATSAPP_TOKEN=                    # постоянный System User token
WHATSAPP_PHONE_NUMBER_ID=          # ID бизнес-номера из Meta
WHATSAPP_TEMPLATES_JSON=[]         # разрешённые шаблоны, описаны ниже
```

GET-проверка callback использует `WHATSAPP_VERIFY_TOKEN`. POST-события Meta
подписывает `WHATSAPP_APP_SECRET`; бэкенд проверяет `X-Hub-Signature-256`.
В Render задайте эти переменные в настройках бэкенда.

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

Для локальной эмуляции используйте отдельный тестовый App Secret и подпишите
им точные байты JSON-пакета HMAC-SHA256.

**Исходящие** — откройте WhatsApp-диалог в «Коммуникациях» и отправьте ответ.
После успешного ответа Graph API CRM покажет «Принято каналом».
Подписанные события Meta обновят статус на «Передано WhatsApp»,
«Доставлено», «Прочитано» или «Ошибка доставки». В Meta для входящих
сообщений и статусов исходящих нужна подписка на поле `messages`.

## Одобренные шаблоны для начала диалога

1. В WhatsApp Manager подтвердите, что шаблон одобрен Meta и согласован
   компанией. Возьмите его точное имя и код языка.
2. Добавьте в `WHATSAPP_TEMPLATES_JSON` JSON-массив объектов. Поля
   `name` и `language` содержат имя и язык из Meta, `label` — название
   в CRM, `parameters` — подписи текстовых заполнителей тела сообщения.
   Перечислите их в порядке от первого к последнему. При отсутствии
   заполнителей укажите пустой массив. Шаблоны с параметрами заголовков,
   кнопок и медиа требуют дополнительной поддержки.
3. В CRM выберите WhatsApp и нажмите «Шаблон WhatsApp». Укажите номер в
   международном формате, заполните параметры и проверьте, что получатель
   согласился на сообщения. После отправки запись появится в диалоге.

## Частые ошибки Meta

| Код | Причина | Решение |
|---|---|---|
| 131026 | получатель не имеет WhatsApp / не принял шаблон | проверить номер |
| 132000 | вне 24-часового окна диалога | слать approved template |
| 131013 | номер получателя в списке тестовых не найден | добавить в Manage test numbers |
| 190 / 401 | токен истёк | перевыпустить System User token |
| не проходит GET-проверка | Verify token отличается от WHATSAPP_VERIFY_TOKEN | сверить значения |
| POST-подпись не проходит | WHATSAPP_APP_SECRET отличается от App Secret | сверить секрет приложения Meta |

## Структура файлов

- `backend/whatsapp_client.py` — Graph API для текста и шаблонов.
- `backend/whatsapp_templates.py` — список разрешённых шаблонов и хранение статусов доставки.
- `backend/main.py` — `/webhooks/whatsapp` (POST приём, GET верификация),
  `POST /api/comms/{id}/send` для WhatsApp, `/api/comms/whatsapp/templates` и `/api/capabilities`
- Фронт показывает баннер «не настроен» с текстом конкретной ошибки Meta.

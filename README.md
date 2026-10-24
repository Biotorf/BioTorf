<div align="center">

# 🌱 BIOTORF Business OS

**CRM-платформа для агрохимического бизнеса** — звонки, Telegram, WhatsApp и сделки в одном окне

`v1.1 · Docker-ready · FastAPI + Vue 3`

ОсОО «Агро Трейд Плюс» · направление BIOTORF

</div>

---

## ✨ Что это

Единое рабочее пространство отдела продаж: все коммуникации с клиентами (телефония, мессенджеры) падают прямо в CRM — не нужно искать абонента в телефонной книге или переключаться между приложениями.

| Модуль | Возможности |
|---|---|
| 📞 **Коммуникации** | Входящие/исходящие звонки, Telegram, WhatsApp в общей ленте; автопривязка к клиенту по номеру; резюме звонков; непрочитанные |
| 👥 **Клиенты и хозяйства** | Реестр хозяйств, контакты, лиды |
| 💼 **Сделки** | Воронка: квалификация → КП → счёт → оплата → доставка |
| 🌾 **Агрономия** | Пилоты, обработки, результаты |
| 📋 **Задачи и календарь** | Поручения, сроки, уведомления о просрочках |
| 🔐 **Роли** | Директор, РОП, менеджер, агроном, маркетинг — меню и права зависят от роли |

## 🏗 Архитектура

```
┌─────────────────────┐         ┌──────────────────────┐
│  Frontend  Vue 3    │  HTTP   │  Backend  FastAPI    │
│  Nginx :8080        │◄───────►│  Uvicorn :8787       │
│  (biotorf-os/)      │  /api   │  SQLite volume       │
└─────────────────────┘         └──────────┬───────────┘
                                           ▲ вебхуки
                    ┌──────────────────────┼──────────────────┐
                    │                      │                  │
              IP-телефония          Telegram Bot API   WhatsApp Cloud API
              (Asterisk/UIS/Манго)  (worker long-poll)  (подпись HMAC)
```

| Слой | Технологии | Каталог |
|---|---|---|
| Фронтенд | Vue 3, Pinia, Vite, Nginx | `biotorf-os/` |
| Бэкенд | FastAPI, SQLite, httpx | `backend/` |
| Инфраструктура | Docker Compose | `docker-compose.yml` |

## 🚀 Быстрый старт (Docker)

```bash
git clone https://github.com/Biotorf/BioTorf.git
cd BioTorf
cp .env.example .env
docker compose up -d --build
```

Готово ✅ — приложение доступно на **http://localhost:8080**, Swagger API — на **http://localhost:8080/docs**.

Подробности: [README-DOCKER.md](README-DOCKER.md) · [DOCKER.md](DOCKER.md) · [Запуск в Docker Desktop (пошагово)](README-DOCKER-DESKTOP.md) · [Подключение Telegram](TELEGRAM.md) · [Подключение WhatsApp](README-WHATSAPP.md)

## 🧪 Как проверить, что коммуникации работают

**1. Наполнить ленту тестовыми данными:**

```bash
curl -X POST http://localhost:8787/api/dev/seed
```

Откройте http://localhost:8080 → раздел **«Коммуникации»** — звонки, Telegram и WhatsApp с автопривязкой к клиентам.

**2. Сымитировать входящий звонок (вебхук телефонии):**

```bash
curl -X POST "http://localhost:8787/webhooks/telephony?token=dev-telephony-token" \
  -H "Content-Type: application/json" \
  -d '{"caller":"+996700112233","callee":"+996312500050","direction":"inbound","duration":95,"status":"answered","timestamp":"2026-10-24T10:15:00+06:00"}'
```

**3. Сымитировать сообщение Telegram:**

```bash
curl -X POST "http://localhost:8787/webhooks/telegram?secret=dev-tg-secret" \
  -H "Content-Type: application/json" \
  -d '{"update_id":1,"message":{"from":{"id":42,"first_name":"Иван","phone_number":"+996700112233"},"text":"Здравствуйте! Интересует биогумус 50 мешков.","date":1761000000}}'
```

Оба события мгновенно появятся в ленте и привяжутся к нужному хозяйству по номеру телефона. 🎯

## 🔌 Боевые интеграции

| Сервис | Как подключить | Эндпоинт |
|---|---|---|
| 📞 Телефония | CDR/события → webhook (Asterisk, UIS, Манго) | `POST /webhooks/telephony?token=<секрет>` |
| ✈️ Telegram | Токен бота в `.env` + воркер | `python3 backend/telegram_worker.py` |
| 💬 WhatsApp | Meta App Secret + callback URL | `POST /webhooks/whatsapp` |

Перед продакшеном замените dev-секреты в `.env` на случайные строки и поднимите HTTPS.

## 📂 Структура репозитория

```
BioTorf/
├── docker-compose.yml      # стек: frontend + backend + tg-worker
├── .env.example            # конфигурация секретов и портов
├── backend/                # FastAPI API + вебхуки + SQLite
│   ├── main.py             # маршруты /api/* и /webhooks/*
│   ├── db.py               # схема и доступ к базе
│   └── telegram_worker.py  # long-poll воркер Bot API
├── biotorf-os/             # Vue 3 SPA (роуты, стores, api-клиент)
├── README-DOCKER.md        # полный гайд по Docker-стеку
├── README-DOCKER-DESKTOP.md # пошаговая привязка и запуск в Docker Desktop
├── DOCKER.md               # архитектурные заметки
├── TELEGRAM.md             # подключение Telegram-бота к ленте коммуникаций
├── README-WHATSAPP.md      # подключение WhatsApp Business Cloud API
└── BIOTORF_Business_OS_demo_v0.9.html  # автономный демо-прототип
```

## 📄 Лицензия и контакты

Внутренний продукт ОсОО «Агро Трейд Плюс», направление BIOTORF. Демонстрационная версия — не содержит реальных персональных данных.

"""BIOTORF Business OS · backend v0.1 — сервис коммуникаций.

REST API для ленты «Коммуникации» (звонки + Telegram + WhatsApp) и входящие
вебхуки от интеграций. Хранилище — SQLite (backend/comms.db).

Запуск:
    cd backend
    pip install -r requirements.txt
    uvicorn main:app --reload --port 8787

Вебхуки (заполните секреты в .env / переменных окружения):
    POST /webhooks/telegram   — Telegram Bot API (getUpdates-воркер или webhook)
    POST /webhooks/whatsapp   — WhatsApp Business Cloud API
    POST /webhooks/telephony  — IP-телефония (любой конструктор CDR, см. normalize_cdr)

Проверка:
    GET  /health
    GET  /api/comms
    docs: http://localhost:8787/docs
"""

import hashlib
import hmac
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import db as store
import logistics
import crm
import whatsapp_client

# ── конфигурация ─────────────────────────────────────────────────────────────
def _env(name: str, default: str = "") -> str:
    # приоритет: переменные окружения (Docker compose задаёт их явно), затем файл .env
    val = os.environ.get(name)
    if val is not None and val != "":
        return val
    env_file = Path(__file__).resolve().parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                if k.strip() == name:
                    return v.strip().strip('"').strip("'")
    return default


FARMS_FILE = Path(_env("FARMS_FILE", str(Path(__file__).resolve().parent / "farms.json")))

TELEGRAM_SECRET = _env("TELEGRAM_WEBHOOK_SECRET")          # X-Bot-Secret для TG-воркера
WHATSAPP_TOKEN = _env("WHATSAPP_APP_SECRET")               # секрет Meta для проверки подписи
TELEPHONY_TOKEN = _env("TELEPHONY_TOKEN")                  # ?token= для телефонии
TELEGRAM_BOT_TOKEN = (_env("TELEGRAM_BOT_TOKEN") or "").strip()  # токен бота — исходящая отправка из ленты
# ── WhatsApp Cloud API (исходящая отправка из ленты) ──
WHATSAPP_SEND_TOKEN = (_env("WHATSAPP_TOKEN") or "").strip()               # постоянный Access Token Meta
WHATSAPP_PHONE_NUMBER_ID = (_env("WHATSAPP_PHONE_NUMBER_ID") or "").strip()  # id бизнес-номера
CORS_ORIGINS = [o.strip() for o in _env(
    "CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,null").split(",") if o.strip()]

app = FastAPI(title="BIOTORF Business OS · Comms API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


TELEGRAM_BOT_INFO: dict | None = None  # результат getMe при старте (для /health и диагностики)
WHATSAPP_INFO: dict | None = None      # результат проверки конфигурации Cloud API при старте


@app.on_event("startup")
def startup():
    global TELEGRAM_BOT_INFO, WHATSAPP_INFO
    store.init_db()
    with store.connect() as conn:
        logistics.init_tables(conn)
        crm.init_tables(conn)
    # Проверяем токен бота сразу при старте, чтобы проблемы было видно в логах
    # и в /health, а не только когда пользователь попытается ответить.
    if TELEGRAM_BOT_TOKEN:
        try:
            res = tg_api("getMe", {})
            if res.get("ok"):
                TELEGRAM_BOT_INFO = res["result"]
                print(f"[telegram] токен принят: @{TELEGRAM_BOT_INFO.get('username')} "
                      f"(id={TELEGRAM_BOT_INFO.get('id')}) — исходящая отправка активна")
            else:
                print(f"[telegram] ОШИБКА: Telegram отверг TELEGRAM_BOT_TOKEN: "
                      f"{res.get('description')} — ответы в TGsentиться НЕ будут")
        except Exception as e:
            print(f"[telegram] ОШИБКА проверки токена ({e}) — проверьте сеть и TELEGRAM_BOT_TOKEN")
    else:
        print("[telegram] TELEGRAM_BOT_TOKEN пуст — исходящие ответы в Telegram отключены. "
              "Впишите токен из @BotFather в .env и выполните docker compose up -d --force-recreate")
    # Аналогичная диагностика для WhatsApp Cloud API
    WHATSAPP_INFO = whatsapp_client.check_config(WHATSAPP_SEND_TOKEN, WHATSAPP_PHONE_NUMBER_ID)
    if WHATSAPP_INFO["ok"]:
        print(f"[whatsapp] конфигурация принята Meta: номер {WHATSAPP_INFO.get('phone')} "
              f"(id={WHATSAPP_INFO.get('id')}) — исходящая отправка активна")
    else:
        print(f"[whatsapp] исходящая отправка НЕ настроена: {WHATSAPP_INFO['error']}. "
              "Заполните WHATSAPP_TOKEN и WHATSAPP_PHONE_NUMBER_ID в .env (см. README-WHATSAPP.md)")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    return "C-" + str(int(time.time() * 1000))[-10:] + os.urandom(2).hex()


def digits(s: str | None) -> str:
    """Нормализация телефона: только цифры, для поиска клиента."""
    return re.sub(r"\D", "", s or "")


def auto_link(phone: str | None) -> str | None:
    """Автопривязка по номеру телефона к реестру хозяйств (backend/farms.json).

    Реестр клиентов живёт во фронтенде; бэкенд подтягивает snapshot farms из
    файла backend/farms.json (экспортируется фронтендом / админом). Если файла
    нет — автопривязка просто не срабатывает, запись остаётся непривязанной.
    """
    d = digits(phone)
    if len(d) < 6:
        return None
    farms_file = FARMS_FILE
    if farms_file.exists():
        try:
            farms = json.loads(farms_file.read_text())
            for f in farms:
                if digits(f.get("phone")) == d:
                    return f["id"]
        except Exception:
            pass
    return None


# ── модели ───────────────────────────────────────────────────────────────────
class CommIn(BaseModel):
    kind: str = Field(pattern="^(call|telegram|whatsapp)$")
    dir: str = Field("in", pattern="^(in|out)$")
    farmId: str | None = None
    contact: str | None = None
    phone: str | None = None
    handle: str | None = None
    ts: str | None = None
    duration: int = 0
    status: str | None = None
    text: str | None = None
    note: str | None = None
    read: bool = True


class CommPatch(BaseModel):
    farmId: str | None = None
    contact: str | None = None
    phone: str | None = None
    handle: str | None = None
    note: str | None = None
    status: str | None = None
    text: str | None = None
    read: bool | None = None


# ── REST: лента коммуникаций ─────────────────────────────────────────────────
@app.get("/api/comms")
def list_comms(
    kind: str | None = Query(None, pattern="^(call|telegram|whatsapp)$"),
    farmId: str | None = None,
    unreadOnly: bool = False,
    limit: int = Query(200, le=1000),
    offset: int = 0,
):
    items, total = store.list_comms(kind, farmId, unreadOnly, limit, offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@app.get("/api/comms/outbox")
def outbox(kind: str = Query("telegram", pattern="^(telegram|whatsapp)$"), limit: int = Query(20, le=100)):
    """Очередь неотправленных исходящих ответов (забирает telegram_worker)."""
    items = store.pending_outbox(kind, limit)
    return {"items": items, "count": len(items)}


@app.get("/api/comms/{comm_id}")
def get_comm(comm_id: str):
    item = store.get(comm_id)
    if not item:
        raise HTTPException(404, "Коммуникация не найдена")
    return item


@app.post("/api/comms", status_code=201)
def create_comm(body: CommIn):
    item = body.model_dump(exclude_none=True)
    item["id"] = new_id()
    item.setdefault("ts", now_iso())
    item["source"] = "manual"
    if item["kind"] == "call" and not item.get("status"):
        item["status"] = "Разговор"
    return store.insert(item)


@app.patch("/api/comms/{comm_id}")
def patch_comm(comm_id: str, body: CommPatch):
    if not store.get(comm_id):
        raise HTTPException(404, "Коммуникация не найдена")
    return store.update(comm_id, body.model_dump(exclude_unset=True))


@app.delete("/api/comms/{comm_id}", status_code=204)
def delete_comm(comm_id: str):
    if not store.delete(comm_id):
        raise HTTPException(404, "Коммуникация не найдена")


@app.post("/api/comms/read-all")
def read_all():
    return {"updated": store.mark_all_read()}


@app.post("/api/comms/{comm_id}/read")
def mark_read(comm_id: str):
    item = store.update(comm_id, {"read": True})
    if not item:
        raise HTTPException(404, "Коммуникация не найдена")
    return item


@app.post("/api/comms/{comm_id}/link")
def link_comm(comm_id: str, farmId: str = Query(...)):
    item = store.update(comm_id, {"farmId": farmId})
    if not item:
        raise HTTPException(404, "Коммуникация не найдена")
    return item


# ── REST: логистика — поставки и выгрузки (отгрузки) товара ─────────────────
class LogisticsItem(BaseModel):
    skuId: str | None = None
    name: str | None = None
    qty: float = 0
    unit: str | None = None
    price: float | None = None
    note: str | None = None


class LogisticsAct(BaseModel):
    type: str = "Акт приёма-передачи"
    number: str | None = None
    date: str | None = None


class LogisticsIn(BaseModel):
    kind: str = Field(pattern="^(supply|dispatch)$")
    number: str | None = None
    date: str | None = None
    status: str | None = None
    party: str | None = None
    farmId: str | None = None
    orderId: str | None = None
    warehouse: str | None = None
    vehicle: str | None = None
    driver: str | None = None
    base: str | None = None
    note: str | None = None
    act: LogisticsAct | None = None
    items: list[LogisticsItem] = []


def new_log_id(kind: str) -> str:
    prefix = "SUP" if kind == "supply" else "DSP"
    return prefix + "-" + str(int(time.time() * 1000))[-9:] + os.urandom(2).hex().upper()


@app.get("/api/logistics")
def list_logistics(kind: str | None = Query(None, pattern="^(supply|dispatch)$")):
    return {"items": logistics.list_docs(store.connect(), kind)}


@app.post("/api/logistics", status_code=201)
def create_logistics(body: LogisticsIn):
    doc_id = new_log_id(body.kind)
    doc = logistics.upsert_doc(store.connect(), body.model_dump(), doc_id)
    return doc


@app.put("/api/logistics/{doc_id}")
def update_logistics(doc_id: str, body: LogisticsIn):
    existing = logistics.get_doc(store.connect(), doc_id)
    if not existing:
        raise HTTPException(404, "Документ не найден")
    return logistics.upsert_doc(store.connect(), body.model_dump(), doc_id)


@app.delete("/api/logistics/{doc_id}", status_code=204)
def delete_logistics(doc_id: str):
    if not logistics.delete_doc(store.connect(), doc_id):
        raise HTTPException(404, "Документ не найден")


# ── CRM ядро: сквозной процесс и операционные реестры (руководство v0.9) ─────
# Хранилище — SQLite (crm_records), синхронизируется между сотрудниками.

def _check_coll(coll: str) -> str:
    if coll not in crm.COLLECTIONS:
        raise HTTPException(404, f"Неизвестная коллекция: {coll}")
    return coll


@app.get("/api/crm/state")
def crm_state():
    """Полный снимок CRM-данных для первичной загрузки фронтенда."""
    return crm.get_state(store.connect())


@app.post("/api/crm/seed")
def crm_seed(body: dict):
    """Первичное наполнение сервера демо-данными (однократно, пустые коллекции)."""
    conn = store.connect()
    loaded = 0
    for coll in crm.COLLECTIONS:
        items = (body or {}).get(coll)
        if not isinstance(items, list):
            continue
        if crm.list_records(conn, coll):   # не затираем существующие данные
            continue
        for rec in items:
            if rec.get("id"):
                crm.upsert(conn, coll, rec, rec["id"])
                loaded += 1
    return {"loaded": loaded}


@app.put("/api/crm/state")
async def crm_put_state(body: dict):
    """Синхронизация всего состояния клиента с сервером (lastWriteWins)."""
    return crm.put_state(store.connect(), body or {})


@app.get("/api/crm/journeys/{journey_id}/process")
def crm_journey_process(journey_id: str):
    """Собранный сквозной процесс: маршрут + все связанные объекты."""
    proc = crm.build_process(store.connect(), journey_id)
    if not proc:
        raise HTTPException(404, "Маршрут не найден")
    return proc


@app.get("/api/crm/{coll}")
def crm_list(coll: str):
    _check_coll(coll)
    return {"items": crm.list_records(store.connect(), coll)}


@app.post("/api/crm/{coll}", status_code=201)
def crm_create(coll: str, body: dict):
    _check_coll(coll)
    return crm.upsert(store.connect(), coll, body or {})


@app.put("/api/crm/{coll}/{rid}")
def crm_update(coll: str, rid: str, body: dict):
    _check_coll(coll)
    existing = crm.get_record(store.connect(), coll, rid)
    if not existing:
        raise HTTPException(404, "Запись не найдена")
    # PATCH-семантика: присланные поля поверх существующих (иначе PUT терял
    # все поля, не указанные в теле запроса)
    merged = {**existing, **(body or {}), "id": rid}
    return crm.upsert(store.connect(), coll, merged, rid)


@app.delete("/api/crm/{coll}/{rid}", status_code=204)
def crm_delete(coll: str, rid: str):
    _check_coll(coll)
    if not crm.delete(store.connect(), coll, rid):
        raise HTTPException(404, "Запись не найдена")


# ── исходящая отправка: ответ клиенту прямо из ленты ─────────────────────────
class SendIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


def tg_api(method: str, payload: dict) -> dict:
    """Вызов Telegram Bot API (urllib, без внешних зависимостей)."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read() or b"{}")


def send_telegram(item: dict, text: str) -> dict:
    """Отправка сообщения клиенту в Telegram через sendMessage.

    Адресат берётся из payload.chatId исходной входящей записи; если чата ещё
    нет — пробуем username / userIndex (бот напишет первым, как только клиент
    начнёт диалог, сообщение доставится)."""
    if not TELEGRAM_BOT_TOKEN:
        raise HTTPException(503, "TELEGRAM_BOT_TOKEN пуст в .env — впишите токен из @BotFather и выполните docker compose up -d --force-recreate")
    if TELEGRAM_BOT_INFO is None:
        # токен задан, но Telegram его не принял (проверка getMe при старте)
        raise HTTPException(503, "Telegram отверг TELEGRAM_BOT_TOKEN (getMe вернул ошибку) — проверьте токен у @BotFather; подробности в docker logs biotorf-backend")
    payload = item.get("payload") or {}
    chat_id = payload.get("chatId")
    attempts = []
    if chat_id:
        attempts.append({"chat_id": chat_id})
    elif payload.get("username"):
        attempts.append({"chat_id": "@" + payload["username"]})
    elif payload.get("userIndex"):
        attempts.append({"chat_id": payload["userIndex"]})
    else:
        raise HTTPException(422, "Неизвестен адресат Telegram (нет chatId/username)")
    last_err = None
    for a in attempts:
        try:
            res = tg_api("sendMessage", {**a, "text": text, "disable_web_page_preview": True})
            if res.get("ok"):
                return {"sent": True, "via": "telegram", "messageId": res["result"]["message_id"]}
            last_err = res.get("description", "unknown")
        except urllib.error.HTTPError as e:
            last_err = e.read().decode(errors="ignore")[:300]
        except Exception as e:  # network и прочее
            last_err = str(e)
    raise HTTPException(502, f"Telegram не принял сообщение: {last_err}")


def send_whatsapp(item: dict, text: str) -> dict:
    """Отправка сообщения клиенту в WhatsApp через Cloud API (Graph).

    Адресат — телефон входящего сообщения (item.phone). Meta отвечает ошибкой,
    если у получателя нет WhatsApp или прошёл >24ч без его сообщения —
    ошибку видно в логах и в payload записи-ответа (sendError).
    """
    if not WHATSAPP_SEND_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        raise HTTPException(503, "WhatsApp не настроен: заполните WHATSAPP_TOKEN и WHATSAPP_PHONE_NUMBER_ID в .env "
                                 "и выполните docker compose up -d --force-recreate")
    to = item.get("phone")
    if not to:
        raise HTTPException(422, "Неизвестен адресат WhatsApp (у входящей записи нет номера телефона)")
    try:
        res = whatsapp_client.send_message(WHATSAPP_SEND_TOKEN, WHATSAPP_PHONE_NUMBER_ID, to, text)
    except whatsapp_client.WhatsAppError as e:
        raise HTTPException(502, f"WhatsApp/Meta не принял сообщение: {e}")
    msg_id = ((res.get("messages") or [{}])[0]).get("id")
    return {"sent": True, "via": "whatsapp", "messageId": msg_id}


@app.post("/api/comms/{comm_id}/send")
def send_reply(comm_id: str, body: SendIn):
    """Ответить клиенту из ленты: реально отправить в канал и создать
    исходящую запись «ответ» со ссылкой на исходное сообщение (replyTo)."""
    item = store.get(comm_id)
    if not item:
        raise HTTPException(404, "Коммуникация не найдена")
    if item["kind"] == "call":
        raise HTTPException(422, "На звонок нельзя ответить сообщением — зафиксируйте звонок или позвоните")
    if item["dir"] != "in":
        raise HTTPException(422, "Отвечать можно только на входящее сообщение")

    sent = None
    send_error = None
    if item["kind"] == "telegram":
        # Бот умеет писать только тем, кто сам начал с ним диалог, поэтому
        # исходящие идут через outbox: воркер long-poll забирает их и шлёт
        # sendMessage. Если токен прямо здесь настроен — пробуем мгновенно.
        chat_id = (item.get("payload") or {}).get("chatId")
        if TELEGRAM_BOT_TOKEN and chat_id:
            try:
                sent = send_telegram(item, body.text)
            except HTTPException as e:
                send_error = str(e.detail)[:200]  # не удалось напрямую — доставит воркер из outbox
    elif item["kind"] == "whatsapp":
        # В WhatsApp бот может писать только по номеру телефона входящего
        # сообщения; отправляем сразу через Cloud API.
        if WHATSAPP_SEND_TOKEN and WHATSAPP_PHONE_NUMBER_ID:
            try:
                sent = send_whatsapp(item, body.text)
            except HTTPException as e:
                send_error = str(e.detail)[:200]

    reply = {
        "id": new_id(),
        "kind": item["kind"],
        "dir": "out",
        "farmId": item.get("farmId"),
        "contact": item.get("contact"),
        "phone": item.get("phone"),
        "handle": item.get("handle"),
        "ts": now_iso(),
        "text": body.text,
        "read": True,
        "source": "reply",
        "status": "Доставлено" if sent else "В очереди",
        "payload": {
            "replyTo": comm_id,
            "tgMessageId": (sent or {}).get("messageId"),
            "waMessageId": (sent or {}).get("messageId") if (sent or {}).get("via") == "whatsapp" else None,
            "chatId": (item.get("payload") or {}).get("chatId"),
            "userIndex": (item.get("payload") or {}).get("userIndex"),
            **({"sendError": send_error} if send_error else {}),
        },
    }
    saved = store.insert(reply)
    return {"item": saved, "sent": bool(sent), "error": send_error}


class DeliveredIn(BaseModel):
    ok: bool = True
    messageId: int | None = None
    error: str | None = None


@app.post("/api/comms/{comm_id}/delivered")
def mark_delivered(comm_id: str, body: DeliveredIn):
    """Воркер подтверждает доставку ответа клиенту."""
    fields = {"status": "Доставлено" if body.ok else "Ошибка доставки"}
    item = store.get(comm_id)
    if item and (body.messageId or body.error):
        payload = dict(item.get("payload") or {})
        if body.messageId:
            payload["tgMessageId"] = body.messageId
        if body.error:
            payload["sendError"] = body.error[:200]
        fields["payload"] = payload
    item = store.update(comm_id, fields)
    if not item:
        raise HTTPException(404, "Коммуникация не найдена")
    return item


@app.get("/api/capabilities")
def capabilities():
    """Что умеет текущая конфигурация бэкенда (фронт показывает/скрывает кнопки)."""
    return {
        "telegramSend": bool(TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_INFO),
        "telegramBot": (TELEGRAM_BOT_INFO or {}).get("username"),
        "whatsappSend": bool(WHATSAPP_INFO and WHATSAPP_INFO.get("ok")),
        "whatsappPhone": (WHATSAPP_INFO or {}).get("phone"),
        "whatsappError": None if (WHATSAPP_INFO or {}).get("ok") else (WHATSAPP_INFO or {}).get("error"),
    }


@app.get("/api/stats")
def stats():
    return store.stats()


@app.get("/health")
def health():
    return {"ok": True, "service": "biotorf-comms", "version": app.version,
            "db": str(store.DB_PATH), "ts": now_iso()}


# ── защита вебхуков ──────────────────────────────────────────────────────────
def check_secret(provided: str | None, expected: str, name: str):
    if not expected:
        raise HTTPException(503, f"Секрет {name} не настроен на сервере")
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(401, "Неверный секрет вебхука")


def verify_whatsapp_signature(body: bytes, signature: str | None):
    if not WHATSAPP_TOKEN:
        raise HTTPException(503, "WHATSAPP_APP_SECRET не настроен")
    if not signature or not signature.startswith("sha256="):
        raise HTTPException(401, "Отсутствует подпись X-Hub-Signature-256")
    digest = hmac.new(WHATSAPP_TOKEN.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest("sha256=" + digest, signature):
        raise HTTPException(401, "Неверная подпись WhatsApp")


# ── вебхук: Telegram ─────────────────────────────────────────────────────────
# Присылается вашим getUpdates-воркером (или самим Telegram при direct-webhook):
# { "update_id": 123, "message": { "from": {...}, "chat": {...}, "text": "..." } }
@app.post("/webhooks/telegram")
async def telegram_webhook(
    request: Request,
    x_bot_secret: str | None = Header(None),
):
    check_secret(x_bot_secret, TELEGRAM_SECRET, "TELEGRAM_WEBHOOK_SECRET")
    payload = await request.json()
    msg = payload.get("message") or payload.get("channel_post")
    if not msg:
        return {"ignored": True, "reason": "не message-событие"}

    chat = msg.get("chat") or {}
    frm = msg.get("from") or {}
    external_id = str(payload.get("update_id") or msg.get("message_id"))

    item = {
        "id": new_id(),
        "kind": "telegram",
        "dir": "in",
        "contact": " ".join(filter(None, [frm.get("first_name"), frm.get("last_name")])) or None,
        "handle": ("@" + frm["username"]) if frm.get("username") else None,
        "phone": frm.get("phone_number") or None,
        "ts": datetime.fromtimestamp(msg.get("date", time.time()), timezone.utc).isoformat(timespec="seconds"),
        "text": msg.get("text") or msg.get("caption") or "",
        "read": False,
        "source": "webhook:telegram",
        "externalId": external_id,
        # chatId обязателен для исходящей отправки (sendMessage) из ленты;
        # userIndex — запасной вариант, если чат ещё не был создан ботом
        "payload": {
            "chatId": chat.get("id"),
            "username": frm.get("username"),
            "userIndex": frm.get("id"),
        },
    }
    item["farmId"] = auto_link(item["phone"]) or auto_link_handle(item["handle"])
    return store.insert(item)


def auto_link_handle(handle: str | None) -> str | None:
    """Привязка входящего Telegram-сообщения к клиенту по @username.

    Если у клиента в реестре (farms.json) заполнено поле telegram — сообщение
    сразу попадает в карточку клиента, даже без номера телефона."""
    if not handle:
        return None
    h = handle.lstrip("@").lower()
    if not h:
        return None
    try:
        farms = json.loads(FARMS_FILE.read_text()) if FARMS_FILE.exists() else []
        for f in farms:
            tg = str(f.get("telegram") or "").lstrip("@").lower()
            if tg and tg == h:
                return f["id"]
    except Exception:
        pass
    return None


# ── вебхук: WhatsApp Business Cloud API ──────────────────────────────────────
@app.post("/webhooks/whatsapp")
async def whatsapp_webhook(request: Request, x_hub_signature_256: str | None = Header(None)):
    raw = await request.body()
    verify_whatsapp_signature(raw, x_hub_signature_256)
    payload = json.loads(raw)

    created = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            business_phone = (value.get("metadata") or {}).get("display_phone_number", "")
            for msg in value.get("messages", []):
                if msg.get("status") and not msg.get("text"):
                    continue  # статусные события (delivered/read) пока пропускаем
                text = (msg.get("text") or {}).get("body") or \
                    (msg.get("interactive") or {}).get("button_reply", {}).get("title") or ""
                contacts = value.get("contacts") or [{}]
                item = {
                    "id": new_id(),
                    "kind": "whatsapp",
                    "dir": "in",
                    "phone": "+" + digits(msg.get("from", "")),
                    "contact": contacts[0].get("profile", {}).get("name") or contacts[0].get("wa_id"),
                    "ts": datetime.fromtimestamp(int(msg.get("timestamp", time.time())), timezone.utc).isoformat(timespec="seconds"),
                    "text": text,
                    "read": False,
                    "source": "webhook:whatsapp",
                    "externalId": msg.get("id"),
                    "payload": {"to": business_phone},
                }
                item["farmId"] = auto_link(item["phone"])
                created.append(store.insert(item))
    return {"created": len(created)}


# GET-верификация вебхука при настройке в Meta Developers
@app.get("/webhooks/whatsapp")
def whatsapp_verify(hub_mode: str = Query("", alias="hub.mode"),
                    hub_token: str = Query("", alias="hub.verify_token"),
                    hub_challenge: str = Query("", alias="hub.challenge")):
    if hub_mode == "subscribe" and hmac.compare_digest(hub_token, WHATSAPP_TOKEN or "\x00"):
        return int(hub_challenge) if hub_challenge.isdigit() else hub_challenge
    raise HTTPException(403, "Verification failed")


# ── вебхук: IP-телефония (CDR) ───────────────────────────────────────────────
# Универсальный формат: пришлите JSON-массив записей или одну запись:
# { "call_id": "...", "from": "+996...", "to": "+996...", "direction": "inbound",
#   "timestamp": "ISO", "duration": 120, "status": "answered|missed", "recording_url": "..." }
def normalize_cdr(c: dict) -> dict:
    direction = str(c.get("direction", "in")).lower()
    dir_ = "in" if direction.startswith("in") else "out"
    caller = c.get("from") if dir_ == "in" else c.get("to")
    status_raw = str(c.get("status", "")).lower()
    missed = status_raw in ("missed", "no-answer", "busy", "failed", "ring-no-answer") or \
        (int(c.get("duration") or 0) == 0 and dir_ == "in")
    ts = c.get("timestamp") or c.get("date_start") or now_iso()
    return {
        "id": new_id(),
        "kind": "call",
        "dir": dir_,
        "phone": caller,
        "ts": ts,
        "duration": int(c.get("duration") or 0),
        "status": "Пропущенный" if missed else "Разговор",
        "note": c.get("note", ""),
        "read": False,
        "source": "webhook:telephony",
        "externalId": str(c.get("call_id") or c.get("id") or ""),
        "payload": {"recordingUrl": c.get("recording_url")},
    }


@app.post("/webhooks/telephony")
async def telephony_webhook(request: Request, token: str = Query("")):
    check_secret(token, TELEPHONY_TOKEN, "TELEPHONY_TOKEN")
    payload = await request.json()
    calls = payload if isinstance(payload, list) else payload.get("calls", [payload])
    created = []
    for c in calls:
        item = normalize_cdr(c)
        item["farmId"] = auto_link(item["phone"])
        created.append(store.insert(item))
    return {"created": len(created)}


# ── демо-сид: заполнение ленты тестовыми данными ────────────────────────────
# Тестовые записи для ручной проверки ленты (POST /api/dev/seed).
# farmId оставляем null — привязка к клиентам произойдёт через auto_link()
# по номерам из реестра FARMS_FILE (backend/farms.json), как в реальном потоке.
TEST_SEED = [
    {"kind": "call", "dir": "in", "contact": None,
     "phone": "+996 700 112 233", "duration": 260, "status": "Разговор",
     "note": "Вопрос по обработке картофеля на следующей неделе", "read": False},
    {"kind": "telegram", "dir": "in", "contact": None,
     "handle": "@asker_farmer",
     "text": "Добрый день! Когда можно привезти BIOTORF на пробу? Участок 40 га, картофель.",
     "read": False},
    {"kind": "whatsapp", "dir": "out", "contact": None,
     "phone": "+996 555 443 322",
     "text": "Отправляем прайс по фасовке 1 л и 5 л. Условия для розницы — в приложении.",
     "read": True},
    {"kind": "call", "dir": "out", "farmId": None,
     "phone": "+996 312 55 66 77", "duration": 0, "status": "Пропущенный",
     "note": "Перезвонили на неизвестный номер — не дозвонились", "read": True},
    {"kind": "call", "dir": "in", "contact": None,
     "phone": "+996 770 887 665", "duration": 145, "status": "Разговор",
     "note": "Обсудили сроки отгрузки, просит счёт до пятницы", "read": True},
]


@app.post("/api/dev/seed")
def seed():
    """Заполнить ленту тестовыми записями (для ручной проверки UI и вебхуков)."""
    n = 0
    for d in TEST_SEED:
        item = dict(d)
        item["id"] = new_id()
        item["ts"] = now_iso()
        item["source"] = "test-seed"
        if not item.get("farmId"):
            item["farmId"] = auto_link(item.get("phone"))
        store.insert(item)
        n += 1
    return {"seeded": n}


@app.post("/api/dev/reset")
def reset():
    """Полная очистка ленты (dev-инструмент)."""
    store.init_db()
    with store.connect() as conn:
        conn.execute("DELETE FROM comms")
    return {"ok": True}

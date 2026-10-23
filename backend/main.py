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
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import db as store

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


@app.on_event("startup")
def startup():
    store.init_db()


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
        "payload": {"chatId": chat.get("id"), "username": frm.get("username")},
    }
    item["farmId"] = auto_link(item["phone"])
    return store.insert(item)


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
DEMO_SEED = [
    {"kind": "call", "dir": "in", "farmId": "F-001", "contact": "Аскер (владелец)",
     "phone": "+996 700 112 233", "duration": 260, "status": "Разговор",
     "note": "Вопрос по обработке картофеля на следующей неделе", "read": False},
    {"kind": "telegram", "dir": "in", "farmId": "F-001", "contact": "Аскер (владелец)",
     "handle": "@asker_farmer",
     "text": "Добрый день! Когда можно привезти BIOTORF на пробу? Участок 40 га, картофель.",
     "read": False},
    {"kind": "whatsapp", "dir": "out", "farmId": "F-002", "contact": "Розница «Ак-Биле»",
     "phone": "+996 555 443 322",
     "text": "Отправляем прайс по фасовке 1 л и 5 л. Условия для розницы — в приложении.",
     "read": True},
    {"kind": "call", "dir": "out", "farmId": None,
     "phone": "+996 312 55 66 77", "duration": 0, "status": "Пропущенный",
     "note": "Перезвонили на неизвестный номер — не дозвонились", "read": True},
    {"kind": "telegram", "dir": "in", "farmId": None, "handle": "@greenhouse_chui",
     "text": "Здравствуйте, интересует препарат для теплиц (огурец). Работаете с дилерами?",
     "read": False},
    {"kind": "call", "dir": "in", "farmId": "F-003", "contact": "Николай Петрович",
     "phone": "+996 770 887 665", "duration": 145, "status": "Разговор",
     "note": "Обсудили сроки отгрузки, просит счёт до пятницы", "read": True},
]


@app.post("/api/dev/seed")
def seed():
    """Заполнить ленту демо-данными."""
    n = 0
    for d in DEMO_SEED:
        item = dict(d)
        item["id"] = new_id()
        item["ts"] = now_iso()
        item["source"] = "demo"
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

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
import logging
import mimetypes
import os
import re
import shutil
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

import auth
import farms_index
import db as store
import psycopg   # OperationalError — «БД недоступна» в middleware (503 вместо 500)
if store.IS_POSTGRES:
    from pg import check_connection as pg_check
import logistics
import channels
import crm
import users
import whatsapp_client

# Единая точка логирования вместо print(): уровень настраивается переменной
# LOG_LEVEL (по умолчанию INFO; в проде можно поставить WARNING).
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper(),
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("biotorf")

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

# ── авторизация (backend/auth.py): значения из окружения / .env ──
os.environ.setdefault("AUTH_SECRET", _env("AUTH_SECRET"))
os.environ.setdefault("AUTH_PASSWORD", _env("AUTH_PASSWORD"))
os.environ.setdefault("AUTH_TOKEN_TTL", _env("AUTH_TOKEN_TTL", "43200"))
os.environ.setdefault("AUTH_DEFAULT_ROLE", _env("AUTH_DEFAULT_ROLE", "director"))
os.environ.setdefault("DEV_MODE", _env("DEV_MODE"))
auth.AUTH_SECRET = os.environ["AUTH_SECRET"].strip()
auth.AUTH_PASSWORD = os.environ["AUTH_PASSWORD"].strip()
try:
    auth.AUTH_TOKEN_TTL = int(os.environ["AUTH_TOKEN_TTL"] or 43200)
except ValueError:
    auth.AUTH_TOKEN_TTL = 43200
auth.DEV_MODE = os.environ["DEV_MODE"].strip().lower() in ("1", "true", "yes", "on")

# Хранилище медиафайлов (голосовые Telegram): скачанные входящие и запись исходящих.
# Лежит рядом с БД — в Docker это тот же volume /data, файлы переживают пересборку.
MEDIA_DIR = Path(_env("MEDIA_DIR") or (store.DB_PATH.parent / "media"))  # legacy-путь; в Docker задаётся MEDIA_DIR=/data/media


def media_path(media_id: str) -> Path | None:
    """Безопасная резолвка mediaId → путь на диске (только наши файлы .oga/.ogg)."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{4,64}", media_id or ""):
        return None
    for ext in (".oga", ".ogg"):
        p = MEDIA_DIR / f"{media_id}{ext}"
        if p.exists():
            return p
    return None

app = FastAPI(title="BIOTORF Business OS · Comms API", version="0.2.0")


def _ensure_channels_schema():
    try:
        channels.ensure_schema()
    except Exception as e:
        log.warning("[channels] схема не готова: %s", e)


def _ensure_schema():
    """Инициализация схемы (SQLite или PostgreSQL).

    В PG-режиме вызывается из фонового потока с ретраями (_schema_worker),
    а не из startup-хука: если база ещё не поднялась (общий старт в docker
    compose, медленный первый initdb), блокирующий executescript() вешал
    startup, uvicorn не открывал порт, health-check платформы убивал
    контейнер — и весь стек падал через 20–30 секунд после деплоя.

    Атомарность по операторам: раньше один битый оператор в schema.sql
    откатывал всю транзакцию executescript() — база поднималась «наполовину»
    (например, comms есть, chat_drafts нет) и каждый PUT /api/chat/.../draft
    падал в 500, пока фоновый retry не повторял ту же ошибку. Теперь каждый
    оператор применяется отдельно; успех = все известные таблицы созданы,
    иначе — False и повтор. Успех логируется списком таблиц — по этой строке
    в логах видно, что схема полная."""
    try:
        store.init_db()
        with store.connect() as conn:
            logistics.init_tables(conn)
            crm.init_tables(conn)
            users.init_tables(conn)
        _ensure_channels_schema()
        if store.IS_POSTGRES:
            missing = _missing_pg_tables()
            if missing:
                log.warning("[db] схема неполная — не созданы таблицы %s; повтор",
                            ", ".join(missing))
                return False
            log.info("[db] схема готова полностью: %s", ", ".join(_PG_SCHEMA_TABLES))
        return True
    except Exception as e:
        log.warning("[db] схема не готова (%s: %s) — повторим в фоновом режиме",
                    type(e).__name__, str(e)[:200])
        return False


# таблицы, которые ОБЯЗАНЫ существовать после успешной инициализации схемы
_PG_SCHEMA_TABLES = ("comms", "chat_drafts", "channels", "channel_accounts",
                     "crm_records", "logistics_docs", "users")


def _missing_pg_tables() -> list[str]:
    """Какие обязательные PG-таблицы ещё не созданы (пустой список = всё ок)."""
    try:
        with store.connect() as conn:
            rows = conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'").fetchall()
        have = {r["table_name"] for r in rows}
        return [t for t in _PG_SCHEMA_TABLES if t not in have]
    except Exception:
        # сама проверка упала (база недоступна) — считаем схему неполной,
        # ретрай повторит позже
        return list(_PG_SCHEMA_TABLES)


def _schema_worker():
    """Фоновая инициализация схемы PG с бесконечным (с ограничением по
    интервалу) retry: сервер поднимается мгновенно, /health отвечает сразу,
    а БД-зависимые эндпоинты начинают работать, как только база оживёт."""
    delay = 2.0
    while not _schema_ready[0]:
        if _ensure_schema():
            _schema_ready[0] = True
            log.info("[db] схема готова")
            return
        time.sleep(delay)
        delay = min(delay * 2, 30.0)


def _users_count_safe() -> int | None:
    """count() сотрудников с защитой от недоступной БД; кэш на 10 секунд —
    иначе каждый /health тратит два медленных таймаута пула при DOWN-базе."""
    now = time.time()
    cached = _USERS_CACHE[0]
    if cached is not None and now - _USERS_CACHE[1] < 10:
        return cached
    try:
        n = users.count()
        _USERS_CACHE[0], _USERS_CACHE[1] = n, now
        return n
    except Exception as e:
        log.warning("[health] users.count() недоступен: %s", str(e)[:120])
        return None


_USERS_CACHE: list = [None, 0.0]   # [значение, timestamp]


_schema_ready = [False]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


TELEGRAM_BOT_INFO: dict | None = None  # результат getMe при старте (для /health и диагностики)
WHATSAPP_INFO: dict | None = None      # результат проверки конфигурации Cloud API при старте


# ── аутентификация HTTP-запросов к /api/* ────────────────────────────────────
# /auth/me требует токен (остальные /auth/* — публичные: login/register)
PUBLIC_PATHS = ("/health", "/docs", "/openapi.json", "/redoc", "/webhooks/",
                "/auth/login", "/auth/register")


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Единая проверка JWT для всех /api/*. Вебхуки (/webhooks/*), /health,
    /docs и /auth/login защищены своими механизмами (секреты/подписи) и
    проходят без токена.

    Режимы:
      • в системе есть зарегистрированные сотрудники (таблица users) —
        принимаются только токены, выпущенные этим сервером этим сотрудникам;
      • сотрудников ещё нет и задан AUTH_PASSWORD — прежний режим общего
        пароля (первый вошедший = временный админ до регистрации);
      • DEV_MODE=1            — локальная разработка без пароля: пустой
        Authorization трактуется как director;
      • ничего не настроено   — LOCKED: /api/* отклоняются с 503.
    """
    t0 = time.perf_counter()
    path = request.url.path
    if not _schema_ready[0]:
        # Ленивая инициализация схемы (запуск без lifespan-событий). В PG-режиме
        # она не должна вешать запрос: при недоступной базе _ensure_schema()
        # возвращает False, а фоновый _schema_worker повторит попытку сам.
        if _ensure_schema():
            _schema_ready[0] = True
    try:
        response = await _auth_middleware_inner(request, call_next, path)
    except HTTPException:
        # ожидаемые ошибки API (401/403/404/422) — не авария, не логируем стек
        raise
    except psycopg.OperationalError as e:
        # База недоступна (или пул исчерпан): это штатная деградация, а не
        # баг хендлера — отдаём 503 без трейсбека на каждый запрос фронта,
        # иначе лог тонет в «Unhandled ... PoolTimeout», а мониторинг
        # поднимает шум из-за 5xx.
        log.warning("[http] %s %s -> 503 (БД недоступна: %.120s)",
                    request.method, path, str(e))
        return JSONResponse(status_code=503, content={
            "detail": f"База данных временно недоступна: {type(e).__name__}: "
                      f"{str(e)[:200]} — повторите позже"})
    except Exception as e:
        # Раньше любое необработанное исключение внутри хендлера превращалось
        # FastAPI в «Internal Server Error» без единой строки в логе — по
        # одному лишь коду ответа было невозможно понять, что упало. Теперь
        # каждый 500 попадает в лог с полным трейсбеком (видно файл/строку),
        # а в ответе остаётся текст ошибки — его видно прямо в браузере
        # (DevTools → Network) и в curl.
        log.exception("[http] Unhandled %s %s", request.method, path)
        return JSONResponse(status_code=500, content={
            "detail": f"Внутренняя ошибка сервера: {type(e).__name__}: "
                      f"{str(e)[:200]} — подробности в логах бэкенда"})
    # структурированный access-log: метод, путь, код, длительность — по нему
    # видно, какие эндпоинты деградировали и когда начались 5xx
    ms = (time.perf_counter() - t0) * 1000
    if response.status_code >= 500:
        log.warning("[http] %s %s -> %d (%.0fms)",
                    request.method, path, response.status_code, ms)
    else:
        log.info("[http] %s %s -> %d (%.0fms)",
                 request.method, path, response.status_code, ms)
    return response


async def _auth_middleware_inner(request: Request, call_next, path: str):
    if request.method == "OPTIONS" or not path.startswith("/api/"):
        return await call_next(request)
    if any(path.startswith(p) for p in PUBLIC_PATHS):
        return await call_next(request)
    has_users = users.count() > 0
    if not auth.AUTH_PASSWORD and not auth.DEV_MODE and not has_users:
        return JSONResponse(status_code=503, content={
            "detail": "API заблокирован: зарегистрируйте первого сотрудника "
                      "(он станет генеральным директором) через экран входа "
                      "или задайте AUTH_PASSWORD в .env"})
    hdr = request.headers.get("authorization") or ""
    token = hdr[7:].strip() if hdr.lower().startswith("bearer ") else ""
    if not token and auth.DEV_MODE and not auth.AUTH_PASSWORD and not has_users:
        payload = {"sub": "dev", "role": "director"}
    else:
        payload = auth.verify_token(token) if token else None
        if payload is None:
            return JSONResponse(status_code=401, content={
                "detail": "Требуется авторизация: передайте заголовок "
                          "Authorization: Bearer <token> (POST /auth/login)"})
    request.state.user = payload.get("sub") or "?"
    # профиль своего аккаунта (/api/me/*) доступен ЛЮБОМУ вошедшему, включая
    # pending: он может заполнить данные о себе, пока ждёт выдачи роли
    if path.startswith("/api/me"):
        return await call_next(request)
    # если в системе есть зарегистрированные сотрудники — сверяем токен с
    # живым реестром: снятая директором роль или удалённый аккаунт отзывают
    # доступ немедленно, не дожидаясь истечения TTL токена
    if has_users:
        live = users.get(request.state.user)
        if not live or not live.get("active"):
            return JSONResponse(status_code=401, content={
                "detail": "Аккаунт отозван администратором — войдите заново"})
        # версия токена: смена роли/удаление аккаунта аннулируют старые токены
        if int(payload.get("tv", 0)) != int(live.get("token_version", 0)):
            return JSONResponse(status_code=401, content={
                "detail": "Ваша роль изменена администратором — войдите заново"})
    if payload["role"] == "pending":
        return JSONResponse(status_code=403, content={
            "detail": "Учётная запись ожидает подтверждения роли "
                      "генеральным директором"})
    request.state.role = payload["role"]
    # реестр сотрудников: GET /api/users — только директору (остальные видят
    # мини-профиль и не должны знать состав/логины коллег); выдача ролей и
    # удаление проверяются в самих эндпоинтах
    if path == "/api/users" and request.method == "GET" \
            and getattr(request.state, "role", "") != "director":
        return JSONResponse(status_code=403, content={
            "detail": "Список сотрудников доступен только генеральному директору"})
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        section = auth.section_for(path)
        if section and not auth.can_write(request.state.role, section):
            return JSONResponse(status_code=403, content={
                "detail": f"Роль «{auth.ROLES.get(request.state.role, request.state.role)}» "
                          f"не имеет права изменять раздел «{section}»"})
    return await call_next(request)


def _who(request: Request) -> str:
    return f"[{getattr(request.state, 'user', '?')}/{getattr(request.state, 'role', '?')}]"


class LoginIn(BaseModel):
    user: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class RegisterIn(LoginIn):
    name: str | None = Field(None, max_length=64)


_login_failures: dict[str, tuple[int, int]] = {}  # ip -> (число ошибок, окно до)
_LOGIN_WINDOW = 60
_LOGIN_MAX_FAILS = 10


def _throttle(ip: str, ok: bool):
    """Не более _LOGIN_MAX_FAILS неудачных попыток в минуту на IP (login/register)."""
    now = int(time.time())
    fails, until = _login_failures.get(ip, (0, 0))
    if until and now < until:
        raise HTTPException(429, "Слишком много неудачных попыток — подождите минуту")
    if ok:
        _login_failures.pop(ip, None)
    else:
        fails = fails + 1 if now < until else 1
        _login_failures[ip] = (fails, now + _LOGIN_WINDOW if fails >= _LOGIN_MAX_FAILS else until)


@app.post("/auth/login")
def auth_login(body: LoginIn, request: Request):
    """Обмен учётных данных сотрудника на JWT (подпись HS256, TTL AUTH_TOKEN_TTL).

    Порядок проверки:
      1) таблица users — персональные аккаунты сотрудников (регистрация через
         фронтенд); первая регистрация автоматически получает роль director;
      2) если сотрудников ещё нет, но задан общий AUTH_PASSWORD — прежний
         режим общего пароля (первый вошедший = временный админ);
      3) защита от перебора: не более 10 неудачных попыток в минуту на IP.
    """
    ip = request.client.host if request.client else "?"
    res = users.authenticate(body.user, body.password)
    if res is None and users.count() == 0 and auth.AUTH_PASSWORD:
        legacy = auth.login(body.user, body.password)
        if legacy:
            role = legacy["role"]
            res = {**legacy, "name": body.user.strip(), "tempAdmin": True}
    if not res:
        _throttle(ip, ok=False)
        log.warning("[auth] неудачный вход: user=%r ip=%s", body.user, ip)
        raise HTTPException(401, "Неверный логин или пароль")
    if res.get("pending"):
        # pending получает токен role=pending: middleware пускает его только
        # в /api/me/* (заполнить профиль, пока ждёт подтверждения), остальные
        # разделы — 403, пока директор не выдаст роль
        log.info("[auth] вход ожидающего подтверждения: %s", res["login"])
        return {"pending": True, "token": auth.make_token(res["login"], "pending"),
                "user": res["login"], "name": res["name"],
                "role": "pending", "roleName": "Ожидает подтверждения",
                "expiresIn": auth.AUTH_TOKEN_TTL, "roles": auth.ROLES}
    _throttle(ip, ok=True)
    log.info("[auth] вход: %s role=%s", res["user"], res["role"])
    return res


@app.post("/auth/register", status_code=201)
def auth_register(body: RegisterIn, request: Request):
    """Регистрация сотрудника с фронтенда.

    ПЕРВЫЙ созданный аккаунт автоматически становится генеральным директором
    (роль director). Все последующие — роль «pending»: они могут войти, но
    доступ к данным закрыт, пока директор не выдаст роль в разделе
    «Сотрудники» (PUT /api/users/{login}/role).
    """
    ip = request.client.host if request.client else "?"
    code, payload = users.register(body.user, body.name or "", body.password)
    if code != 201:
        if code == 409:          # дубликат логина — не атака, не троттлим
            raise HTTPException(code, payload["detail"])
        _throttle(ip, ok=False)
        raise HTTPException(code, payload["detail"])
    _throttle(ip, ok=True)
    log.info("[auth] регистрация: %s role=%s%s", payload["login"], payload["role"],
             " (ПЕРВЫЙ АККАУНТ = ГЕНЕРАЛЬНЫЙ ДИРЕКТОР)" if payload["firstAccount"] else "")
    if payload["firstAccount"]:
        # первый сотрудник входит сразу — токен выдаём на месте
        return {"token": auth.make_token(payload["login"], "director"),
                "user": payload["login"], "name": payload["name"],
                "role": "director", "roleName": auth.ROLES["director"],
                "roles": auth.ROLES, "firstAccount": True,
                "expiresIn": auth.AUTH_TOKEN_TTL}
    return {"ok": True, "firstAccount": False, "login": payload["login"],
            "name": payload["name"], "role": "pending",
            "roleName": "Ожидает подтверждения"}


@app.get("/auth/me")
def auth_me(request: Request):
    role = getattr(request.state, "role", "?")
    login_name = getattr(request.state, "user", "?")
    live = users.get(login_name) if users.count() > 0 else None
    return {"user": login_name,
            "name": (live or {}).get("name") or login_name,
            "role": role,
            "roleName": auth.ROLES.get(role, None)}


def _startup_checks():
    """Проверки внешних API (Telegram getMe, WhatsApp config) — в ФОНОВОМ
    потоке, а не в startup-хуке.

    Раньше они выполнялись синхронно при старте: если api.telegram.org или
    graph.facebook.com недоступны/зависают (заблокированная сеть на хостинге,
    нет DNS), uvicorn не завершал startup и НЕ открывал порт — health-check
    платформы не дожидался /health, убивал контейнер, и весь стек падал через
    20–30 секунд после деплоя («работало и упало»). Теперь сервер поднимается
    мгновенно, а диагностика интеграций пишется в лог по мере готовности."""
    global TELEGRAM_BOT_INFO, WHATSAPP_INFO
    if TELEGRAM_BOT_TOKEN:
        try:
            res = tg_api("getMe", {})
            if res.get("ok"):
                TELEGRAM_BOT_INFO = res["result"]
                log.info("[telegram] токен принят: @%s (id=%s) — исходящая отправка активна",
                         TELEGRAM_BOT_INFO.get("username"), TELEGRAM_BOT_INFO.get("id"))
            else:
                log.error("[telegram] Telegram отверг TELEGRAM_BOT_TOKEN: %s — ответы в TG "
                          "отправляться НЕ будут", res.get("description"))
        except Exception as e:
            log.error("[telegram] ОШИБКА проверки токена (%s) — проверьте сеть и TELEGRAM_BOT_TOKEN", e)
    else:
        log.info("[telegram] TELEGRAM_BOT_TOKEN пуст — исходящие ответы в Telegram отключены. "
                 "Впишите токен из @BotFather в .env и выполните docker compose up -d --force-recreate")
    try:
        WHATSAPP_INFO = whatsapp_client.check_config(WHATSAPP_SEND_TOKEN, WHATSAPP_PHONE_NUMBER_ID)
    except Exception as e:
        WHATSAPP_INFO = {"ok": False, "error": f"проверка не выполнена: {e}"}
    if WHATSAPP_INFO["ok"]:
        log.info("[whatsapp] конфигурация принята Meta: номер %s (id=%s) — исходящая отправка активна",
                 WHATSAPP_INFO.get("phone"), WHATSAPP_INFO.get("id"))
    else:
        log.info("[whatsapp] исходящая отправка НЕ настроена: %s. "
                 "Заполните WHATSAPP_TOKEN и WHATSAPP_PHONE_NUMBER_ID в .env (см. README-WHATSAPP.md)",
                 WHATSAPP_INFO["error"])


@app.on_event("startup")
def startup():
    # Только локальные операции — без сети и без блокирующего ожидания БД.
    if store.IS_POSTGRES:
        # В PG-режиме инициализация схемы уходит в фоновый поток с ретраями:
        # если база ещё не поднялась, startup не должен висеть — иначе
        # health-check платформы не дождётся /health и убьёт контейнер.
        threading.Thread(target=_schema_worker, daemon=True).start()
    else:
        _ensure_schema()
        _schema_ready[0] = True
    if not auth.AUTH_PASSWORD and not auth.DEV_MODE:
        log.warning("[auth] ⚠ AUTH_PASSWORD не задан — API ЗАБЛОКИРОВАН (503 на все /api/*). "
                    "Задайте пароль в .env или включите DEV_MODE=1 для локальной разработки.")
    elif auth.AUTH_PASSWORD:
        if len(auth.AUTH_PASSWORD) < 12:
            log.warning("[auth] AUTH_PASSWORD короче 12 символов — используйте длинный случайный пароль")
        if not auth.AUTH_SECRET:
            log.warning("[auth] AUTH_SECRET не задан — подпись JWT выводится из пароля; "
                        "смените пароль = аннулируются все токены. Лучше задать отдельный AUTH_SECRET")
    else:
        log.info("[auth] DEV_MODE: авторизация API ослаблена (только локальная разработка!)")
    threading.Thread(target=_startup_checks, daemon=True).start()


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
    Чтение файла кэшируется по mtime (farms_index), см. также index по @username.
    """
    return farms_index.link_by_phone(FARMS_FILE, phone)


# ── модели ───────────────────────────────────────────────────────────────────
class CommIn(BaseModel):
    kind: str
    dir: str = Field("in", pattern="^(in|out)$")
    payload: dict | None = None
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


class SendIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class VoiceOutboxIn(BaseModel):
    mediaId: str
    duration: int = 0


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
    kind: str | None = Query(None),
    farmId: str | None = None,
    unreadOnly: bool = False,
    limit: int = Query(200, le=1000),
    offset: int = 0,
):
    if kind and kind not in channels.all_kinds():
        return {"items": [], "total": 0}
    items, total = store.list_comms(kind, farmId, unreadOnly, limit, offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@app.get("/api/comms/outbox")
def outbox(kind: str = Query("telegram"), limit: int = Query(20, le=100)):
    """Очередь неотправленных исходящих ответов (забирает telegram_worker)."""
    items = store.pending_outbox(kind, limit)
    return {"items": items, "count": len(items)}


# ── лента событий: входящие с момента последней позиции (long-poll) ────
@app.get("/api/comms/events")
def comms_events(since: int = Query(0, ge=0), limit: int = Query(100, le=500)):
    """Возвращает сообщения с seq > since. Позиция — целая последовательная
    ссылка БД (PostgreSQL identity / SQLite rowid), не зависит от часов клиента.
    Используется фронтендом для надёжного получения входящих Telegram/WhatsApp
    без рассинхрона по ts."""
    with store.connect() as conn:
        rows = conn.execute(
            "SELECT seq, * FROM comms WHERE seq > ? ORDER BY seq ASC LIMIT ?",
            (since, limit),
        ).fetchall()
    items = []
    for r in rows:
        d = store.to_dict(r)
        d["seq"] = r["seq"]
        items.append(d)
    return {"items": items, "maxSeq": rows[-1]["seq"] if rows else since}


# ── мессенджер: чаты (диалоги с клиентами) ───────────────────────────────────
@app.get("/api/chat-list")
def chats_list(limit: int = Query(200, le=500)):
    """Список чатов как в Telegram: по одному диалогу на собеседника,
    последнее сообщение, счётчик непрочитанных, статус доставки ответа."""
    return {"items": store.chats(limit)}


@app.get("/api/chat/{peer_key}")
def chat_detail(peer_key: str):
    for g in store.chats():
        if g["key"] == peer_key:
            return g
    raise HTTPException(404, "Чат не найден")


@app.post("/api/chat/{peer_key}/read")
def chat_read(peer_key: str):
    return {"updated": store.mark_peer_read(peer_key)}


class DraftIn(BaseModel):
    draft: str = Field(default="", max_length=4000)


@app.put("/api/chat/{peer_key}/draft")
def chat_draft(peer_key: str, body: DraftIn):
    """Сохранить черновик ответа — как «неотправленное сообщение» в мессенджере."""
    store.save_draft(peer_key, body.draft, now_iso())
    return {"ok": True}


def chat_send_core(peer_key: str, text: str, media_file: str | None = None):
    """Ядро отправки в чат: ищем адресата чата и доставляем через нужный канал;
    если доставка невозможна прямо сейчас — уходит в outbox воркера."""
    chats = [g for g in store.chats() if g["key"] == peer_key]
    if not chats:
        raise HTTPException(404, "Чат не найден — отправьте первое сообщение через /api/comms")
    target = None
    for m in reversed(chats[0]["messages"]):
        if m["dir"] == "in" and m["kind"] != "call":
            target = m
            break
    if target is None:  # исходящих нет? берём любую входящую не-звонковую
        raise HTTPException(422, "В чате нет входящего сообщения-адресата для ответа")
    if media_file and target["kind"] != "telegram":
        raise HTTPException(422, "Голосовые сообщения поддерживаются только в Telegram-чатах")
    res = send_reply(target["id"], SendIn(text=text), media_file=media_file)
    return res


@app.post("/api/chat/{peer_key}/send")
def chat_send(peer_key: str, body: "SendIn"):
    """Отправить сообщение в чат напрямую (из окна диалога мессенджера)."""
    return chat_send_core(peer_key, body.text)


# ── голосовые сообщения (Telegram) ───────────────────────────────────────────
VOICE_MAX_BYTES = 10 * 1024 * 1024  # 10 МБ — больше любой разумной войсолевой


@app.post("/api/chat/{peer_key}/send-voice")
async def chat_send_voice(
    peer_key: str,
    file: UploadFile = File(...),
    duration: int = Form(0),
    caption: str = Form(""),
):
    """Записать и отправить голосовое сообщение клиенту в Telegram.

    Фронтенд пишет микрофон MediaRecorder в webm/opus; бэкенд перекодирует в
    Ogg Opus (.oga) через ffmpeg — только этот формат Telegram показывает как
    «голосовое» с волной. Без ffmpeg файл уйдёт как обычное аудио-вложение."""
    raw = await file.read(VOICE_MAX_BYTES + 1)
    if len(raw) > VOICE_MAX_BYTES:
        raise HTTPException(413, "Запись больше 10 МБ")
    if not raw:
        raise HTTPException(422, "Пустой аудиофайл")
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    media_id = os.urandom(8).hex()
    src = MEDIA_DIR / f"{media_id}.src"
    dst = MEDIA_DIR / f"{media_id}.oga"
    src.write_bytes(raw)
    try:
        conv = _ffmpeg_to_oga(src, dst)
        if not conv:
            # ffmpeg недоступен — отдаём как есть (TG покажет аудио файлом)
            shutil.copyfile(src, dst)
        as_voice = conv
        res = chat_send_core(peer_key, (caption or "").strip() or "🎤 Голосовое сообщение",
                             media_file=str(dst) if as_voice else None)
        item = res.get("item") or {}
        if item.get("id"):
            payload = dict(item.get("payload") or {})
            payload["media"] = {"mediaId": media_id, "mimeType": "audio/ogg",
                                "size": dst.stat().st_size, "duration": max(0, min(int(duration or 0), 3600)),
                                "asVoice": as_voice}
            store.update(item["id"], {"payload": payload})
            res["media"] = payload["media"]
        return res
    finally:
        try:
            src.unlink(missing_ok=True)
        except OSError:
            pass


def _ffmpeg_to_oga(src: Path, dst: Path) -> bool:
    """Перекодировать запись микрофона в Ogg Opus — формат голосовых Telegram."""
    import subprocess
    if not shutil.which("ffmpeg"):
        return False
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", str(src), "-ac", "1", "-ar", "48000",
             "-c:a", "libopus", "-b:a", "32k", "-application", "voip", str(dst)],
            capture_output=True, timeout=60,
        )
        return r.returncode == 0 and dst.exists() and dst.stat().st_size > 0
    except Exception as e:
        log.warning("[voice] ffmpeg failed: %s", e)
        return False


@app.post("/api/comms/{comm_id}/attach-voice")
def attach_voice(comm_id: str, body: VoiceOutboxIn):
    """Привязать записанный медиафайл к исходящему сообщению (для повтора воркером)."""
    p = media_path(body.mediaId)
    if not p:
        raise HTTPException(404, "Медиафайл не найден")
    item = store.get(comm_id)
    if not item or item["dir"] != "out":
        raise HTTPException(404, "Исходящее сообщение не найдено")
    payload = dict(item.get("payload") or {})
    payload["media"] = {"mediaId": body.mediaId, "mimeType": "audio/ogg",
                        "duration": max(0, min(int(body.duration or 0), 3600))}
    updated = store.update(comm_id, {"payload": payload})
    return updated or item


@app.get("/api/media/{media_id}")
def get_media(media_id: str):
    """Отдать голосовое сообщение на прослушивание (input-stream для <audio>)."""
    p = media_path(media_id)
    if not p:
        raise HTTPException(404, "Медиафайл не найден")
    guess = mimetypes.guess_type(str(p))[0] or "audio/ogg"
    return FileResponse(p, media_type=guess,
                        headers={"Content-Disposition": f'inline; filename="{p.name}"'})



@app.get("/api/comms/{comm_id}")
def get_comm(comm_id: str):
    item = store.get(comm_id)
    if not item:
        raise HTTPException(404, "Коммуникация не найдена")
    return item


@app.post("/api/comms", status_code=201)
def create_comm(body: CommIn):
    item = body.model_dump(exclude_none=True)
    if not channels.valid_kind(item["kind"]):
        raise HTTPException(422, f"Неизвестный или отключённый канал «{item['kind']}». "
                                 "Подключите его в Настройках (Каналы CRM).")
    item["id"] = new_id()
    item.setdefault("ts", now_iso())
    item["source"] = "manual"
    if item["kind"] == "call" and not item.get("status"):
        item["status"] = "Разговор"
    if not item.get("farmId"):
        item["farmId"] = (auto_link(item.get("phone"))
                          or crm.auto_link_tg(store.connect(), item.get("handle"), item.get("phone")))
    saved = store.insert(item)
    try:
        crm.register_comm(store.connect(), saved)
    except Exception as e:
        log.warning("[crm] register_comm skip: %s", e)
    return saved


@app.patch("/api/comms/{comm_id}")
def patch_comm(comm_id: str, body: CommPatch):
    if not store.get(comm_id):
        raise HTTPException(404, "Коммуникация не найдена")
    return store.update(comm_id, body.model_dump(exclude_unset=True))


@app.delete("/api/comms/{comm_id}", status_code=204)
def delete_comm(comm_id: str):
    if not store.delete(comm_id):
        raise HTTPException(404, "Коммуникация не найдена")


# ── Реестр каналов и подключённые аккаунты (CRM-настройки) ───────────────────
@app.get("/api/channels")
def api_channels(enabled_only: bool = Query(False)):
    """Список каналов с подключёнными аккаунтами (секреты наружу не отдаются)."""
    return {"items": channels.list_channels(include_disabled=not enabled_only),
            "presets": channels.CHANNEL_PRESETS}


@app.post("/api/channels", status_code=201)
def api_channels_add(kind: str = Query(...), body: dict = ...):
    try:
        return channels.add_channel(kind, body)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except KeyError:
        raise HTTPException(409, "Канал уже существует")


@app.patch("/api/channels/{kind}")
def api_channels_patch(kind: str, body: dict):
    try:
        return channels.patch_channel(kind, body)
    except KeyError:
        raise HTTPException(404, "Канал не найден")


@app.post("/api/channels/{kind}/accounts", status_code=201)
def api_channel_connect(kind: str, body: dict, request: Request):
    try:
        acc = channels.connect_account(kind, body, who=_who(request))
    except ValueError as e:
        raise HTTPException(422, str(e))
    except KeyError:
        raise HTTPException(404, "Канал не найден. Добавьте его в списке каналов.")
    # телеграм: проверить токен живым запросом getMe (graceful — если сети нет)
    if kind == "telegram" and acc.get("tokenMask"):
        threading.Thread(target=_verify_tg_account, args=(body.get("token", ""),), daemon=True).start()
    return acc


@app.patch("/api/channel-accounts/{account_id}")
def api_channel_account_update(account_id: str, body: dict):
    try:
        return channels.update_account(account_id, body)
    except KeyError:
        raise HTTPException(404, "Аккаунт не найден")


@app.delete("/api/channel-accounts/{account_id}", status_code=204)
def api_channel_account_delete(account_id: str):
    try:
        channels.delete_account(account_id)
    except KeyError:
        raise HTTPException(404, "Аккаунт не найден")


def _verify_tg_account(token: str):
    try:
        res = tg_api("getMe", {}, token_override=token)
        if res.get("ok"):
            log.info("[channels] telegram-аккаунт @%s подтверждён", res["result"].get("username"))
    except Exception as e:
        log.warning("[channels] проверка telegram-токена: %s", e)


# generic входящий вебхук для любого канала (instagram/vk/avito/… через n8n/Zapier/скрипт)
@app.post("/webhooks/channel/{kind}")
async def webhook_channel(kind: str, request: Request,
                          x_webhook_secret: str = Header(None),
                          secret: str = Query(None)):
    """Приём сообщений из любого канала. Тело: {kind?, dir?, contact?, handle?,
    phone?, text, ts?, externalId?, payload?}. Секрет — заголовок X-Webhook-Secret."""
    if not channels.valid_kind(kind):
        raise HTTPException(404, "Канал не найден или отключён. Подключите его в Настройках.")
    expected = channels.get_secret(kind, field="secret") or ""
    got = x_webhook_secret or secret or ""
    if expected and not hmac.compare_digest(expected, got):
        raise HTTPException(401, "Неверный секрет вебхука")
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(422, "Ожидается JSON-объект")
    item = {
        "kind": body.get("kind") or kind,
        "dir": body.get("dir", "in"),
        "contact": body.get("contact"), "handle": body.get("handle"),
        "phone": body.get("phone"), "text": body.get("text") or "",
        "ts": body.get("ts") or now_iso(),
        "externalId": body.get("externalId"),
        "source": f"webhook:{kind}",
        "payload": body.get("payload"),
    }
    if not item["text"]:
        raise HTTPException(422, "Поле text обязательно")
    item["id"] = new_id()
    if not item.get("farmId"):
        item["farmId"] = (auto_link(item.get("phone"))
                          or crm.auto_link_tg(store.connect(), item.get("handle"), item.get("phone")))
    saved = store.insert(item)
    try:
        crm.register_comm(store.connect(), saved)
    except Exception as e:
        log.warning("[crm] register_comm skip: %s", e)
    return {"ok": True, "id": saved["id"]}


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
    with store.connect() as conn:
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
    try:
        return crm.upsert(store.connect(), coll, body or {})
    except crm.ConflictError as e:
        raise HTTPException(409, f"Запись «{e.rid}» уже изменена другим пользователем — обновите данные")


@app.put("/api/crm/{coll}/{rid}")
def crm_update(coll: str, rid: str, body: dict):
    _check_coll(coll)
    existing = crm.get_record(store.connect(), coll, rid)
    if not existing:
        raise HTTPException(404, "Запись не найдена")
    # PATCH-семантика: присланные поля поверх существующих (иначе PUT терял
    # все поля, не указанные в теле запроса)
    merged = {**existing, **(body or {}), "id": rid}
    try:
        return crm.upsert(store.connect(), coll, merged, rid)
    except crm.ConflictError as e:
        raise HTTPException(409, f"Запись «{e.rid}» уже изменена другим пользователем — обновите данные")


@app.delete("/api/crm/{coll}/{rid}", status_code=204)
def crm_delete(coll: str, rid: str):
    _check_coll(coll)
    if not crm.delete(store.connect(), coll, rid):
        raise HTTPException(404, "Запись не найдена")


# ── исходящая отправка: ответ клиенту прямо из ленты ─────────────────────────
# Жёсткий сетевой дедлайн для исходящих HTTP-вызовов. Обычный timeout у
# urlopen покрывает только чтение/запись сокета, но НЕ сам TCP-connect к мёртвому
# хосту (blackhole-маршрутизация на хостинге): connect зависает на системных
# ~2 мин, игнорируя timeout. Все эндпоинты синхронные и выполняются в threadpool
# uvicorn (~40 потоков): несколько зависших вызовов к api.telegram.org во время
# сетевых проблем занимали пул, и даже /health переставал отвечать — nginx/OneReza
# фиксировали 502 и убивали контейнер («работает 20–30 секунд и падает»).
# settimeout после соединения покрывает И connect, и чтение одним интервалом.
NET_TIMEOUT = float(os.environ.get("NET_TIMEOUT", "6"))


def _open(req, timeout: float):
    """urlopen с гарантированным дедлайном (включая стадию TCP-connect)."""
    if isinstance(req, str):
        req = urllib.request.Request(req)
    conn = urllib.request.urlopen(req, timeout=timeout)
    try:
        conn.fp._sock.settimeout(timeout)      # http.client.HTTPResponse
    except Exception:
        pass
    return conn


def tg_api(method: str, payload: dict, token_override: str | None = None) -> dict:
    """Вызов Telegram Bot API (urllib, без внешних зависимостей).

    token_override — токен подключённого аккаунта из реестра каналов; если не
    задан, используется TELEGRAM_BOT_TOKEN из окружения (обратная совместимость)."""
    token = token_override or channels.get_secret("telegram") or TELEGRAM_BOT_TOKEN
    url = f"https://api.telegram.org/bot{token}/{method}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    # Короткий жёсткий таймаут (см. NET_TIMEOUT): зависшие вызовы Telegram при
    # проблемах сети не должны занимать потоки threadpool — иначе даже /health
    # не получал ответа и nginx отдавал 502 «Бэкенд недоступен».
    with _open(req, NET_TIMEOUT) as resp:
        return json.loads(resp.read() or b"{}")


def send_telegram(item: dict, text: str, media_file: str | None = None) -> dict:
    """Отправка сообщения клиенту в Telegram через sendMessage.

    Если передан media_file (локальный путь к .oga) — отправляем голосовое
    сообщение через sendVoice (Telegram отобразит его как плеер с волной).
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
            if media_file:
                res = tg_send_voice(a, media_file)
            else:
                res = tg_api("sendMessage", {**a, "text": text, "disable_web_page_preview": True})
            if res.get("ok"):
                return {"sent": True, "via": "telegram", "messageId": res["result"]["message_id"]}
            last_err = res.get("description", "unknown")
        except urllib.error.HTTPError as e:
            last_err = e.read().decode(errors="ignore")[:300]
        except Exception as e:  # network и прочее
            last_err = str(e)
    raise HTTPException(502, f"Telegram не принял сообщение: {last_err}")


def tg_send_voice(attempt: dict, media_file: str) -> dict:
    """multipart-вызов Bot API sendVoice (JSON-методы getFile/upload не принимают)."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVoice"
    boundary = "----biotorf" + os.urandom(8).hex()
    fname = Path(media_file).name
    data = Path(media_file).read_bytes()
    parts = []
    for k, v in attempt.items():
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    parts.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"voice\"; filename=\"{fname}\"\r\n"
        f"Content-Type: audio/ogg\r\n\r\n".encode()
    )
    parts.append(data)
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    body = b"".join(parts)
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    # sendVoice —multipart-загрузка голоса: чуть длиннее дедлайн, но всё равно
    # жёсткий (см. NET_TIMEOUT), чтобы не вешать потоки threadpool навсегда.
    with _open(req, max(NET_TIMEOUT, 20)) as resp:
        return json.loads(resp.read() or b"{}")


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


def send_reply(comm_id: str, body: SendIn, media_file: str | None = None):
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
                sent = send_telegram(item, body.text, media_file=media_file)
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


@app.post("/api/comms/{comm_id}/send")
def send_reply_http(comm_id: str, body: SendIn):
    """HTTP-эндпоинт ответа из ленты (текст)."""
    return send_reply(comm_id, body)


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


@app.post("/api/comms/send-to")
def send_to(body: dict):
    """Начать диалог из мессенджера с клиентом, у которого ещё нет переписки:
    { kind: telegram|whatsapp, chatId?|username?|userIndex?|phone?, contact?, farmId?, text }"""
    kind = body.get("kind")
    text = (body.get("text") or "").strip()
    if kind not in ("telegram", "whatsapp") or not text:
        raise HTTPException(422, "Укажите kind (telegram/whatsapp) и текст сообщения")
    pl = {}
    if kind == "telegram":
        if body.get("chatId"):
            pl["chatId"] = body["chatId"]
        elif body.get("username"):
            pl["username"] = str(body["username"]).lstrip("@")
        elif body.get("userIndex"):
            pl["userIndex"] = body["userIndex"]
        else:
            raise HTTPException(422, "Неизвестен адресат Telegram (нужен chatId или @username)")
    else:
        if not body.get("phone"):
            raise HTTPException(422, "Для WhatsApp нужен номер телефона получателя")
    item = {
        "id": new_id(),
        "kind": kind,
        "dir": "out",
        "farmId": body.get("farmId") or auto_link(body.get("phone"))
                  or crm.auto_link_tg(store.connect(), body.get("handle"), body.get("phone")),
        "contact": body.get("contact"),
        "phone": body.get("phone"),
        "handle": ("@" + str(body["username"]).lstrip("@")) if body.get("username") else body.get("handle"),
        "ts": now_iso(),
        "text": text,
        "read": True,
        "source": "chat",
        "status": "В очереди",
        "payload": pl,
    }
    sent = None
    send_error = None
    try:
        if kind == "telegram" and TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_INFO:
            sent = send_telegram(item, text)
        elif kind == "whatsapp" and WHATSAPP_SEND_TOKEN and WHATSAPP_PHONE_NUMBER_ID:
            sent = send_whatsapp(item, text)
    except HTTPException as e:
        send_error = str(e.detail)[:200]
    if sent:
        item["status"] = "Доставлено"
        item["payload"]["tgMessageId"] = sent.get("messageId")
    if send_error:
        item["payload"]["sendError"] = send_error
    saved = store.insert(item)
    return {"item": saved, "sent": bool(sent), "error": send_error}


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


# ── REST: сотрудники и роли (выдача ролей — только генеральному директору) ───
class RoleIn(BaseModel):
    role: str = Field(min_length=2, max_length=32)


@app.get("/api/users")
def users_list(request: Request):
    """Список сотрудников (без хешей паролей). Может смотреть любой
    авторизованный, включая ожидающих подтверждения."""
    return {"items": users.list_all(),
            "roles": auth.ROLES,
            "canManage": getattr(request.state, "role", "") == "director"}


@app.put("/api/users/{login}/role")
def users_set_role(login: str, body: RoleIn, request: Request):
    """Выдать сотруднику роль. Право — только у «director» (генерального
    директора); так же он может снять роль, вернув сотрудника в «pending»."""
    if getattr(request.state, "role", "") != "director":
        raise HTTPException(403, "Роли сотрудников выдаёт только генеральный директор")
    role = body.role.strip()
    if role != "pending" and role not in auth.ROLES:
        raise HTTPException(400, f"Неизвестная роль «{role}»")
    target = users.get(login)
    if not target:
        raise HTTPException(404, "Сотрудник не найден")
    if login == request.state.user and role != "director":
        raise HTTPException(400, "Нельзя понизить собственную роль директора")
    updated = users.set_role(login, role)
    users.bump_token_version(login)   # старые токены недействительны сразу
    log.info("%s выдал роль %s=%s", _who(request), login, role)
    return updated


@app.delete("/api/users/{login}", status_code=204)
def users_delete(login: str, request: Request):
    """Удалить аккаунт сотрудника (только директор; нельзя удалить себя)."""
    if getattr(request.state, "role", "") != "director":
        raise HTTPException(403, "Удалять аккаунты может только генеральный директор")
    if login == request.state.user:
        raise HTTPException(400, "Нельзя удалить собственный аккаунт")
    if not users.delete(login):
        raise HTTPException(404, "Сотрудник не найден")
    log.info("%s удалил аккаунт %s", _who(request), login)


# ── REST: профиль своего аккаунта (доступен и pending-сотрудникам) ───────────
class ProfileIn(BaseModel):
    name: str | None = Field(None, max_length=64)
    position: str | None = Field(None, max_length=64)
    phone: str | None = Field(None, max_length=32)
    email: str | None = Field(None, max_length=64)
    note: str | None = Field(None, max_length=500)


@app.get("/api/me/profile")
def me_profile(request: Request):
    """Карточка своего сотрудника: имя, должность, телефон, e-mail, заметка."""
    u = users.get(request.state.user)
    if not u:
        raise HTTPException(404, "Аккаунт не найден")
    u.pop("pw_hash", None)
    u["roleName"] = auth.ROLES.get(u["role"], "Ожидает подтверждения")
    return u


@app.patch("/api/me/profile")
def me_profile_patch(body: ProfileIn, request: Request):
    """Сотрудник сам заполняет данные своего профиля (PATCH-семантика)."""
    code, payload = users.update_profile(request.state.user, body.model_dump(exclude_unset=True))
    if code != 200:
        raise HTTPException(code, payload.get("detail", "Ошибка"))
    log.info("%s обновил профиль", _who(request))
    return payload


class PasswordIn(BaseModel):
    old_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


@app.post("/api/me/password")
def me_password(body: PasswordIn, request: Request):
    """Смена собственного пароля (требует старый; все сессии при этом отзываються)."""
    code, payload = users.change_password(request.state.user,
                                          body.old_password, body.new_password)
    if code != 200:
        raise HTTPException(code, payload.get("detail", "Ошибка"))
    log.info("%s сменил пароль (все токены отозваны)", _who(request))
    return payload


@app.get("/api/stats")
def stats():
    return store.stats()


@app.get("/health")
def health():
    # Проверка доступности БД не должна вешать запрос: pg.check_connection
    # использует пул с коротким connect_timeout и сразу возвращает ошибку.
    try:
        db_ok, db_msg = pg_check() if store.IS_POSTGRES else (True, "sqlite")
    except Exception as e:  # на всякий случай: health обязан отвечать всегда
        db_ok, db_msg = False, f"{type(e).__name__}: {str(e)[:120]}"
    # authRequired/hasUsers требуют обращения к БД — при недоступной базе
    # эти запросы бросают исключение. Раньше оно выходило наружу и curl
    # получал «500 Internal Server Error». Теперь health всегда отвечает:
    # 200 с деталями, если сервис жив; 503, если база недоступна.
    n_users = _users_count_safe()   # кэш + try/except: не виснет на таймаутах пула
    auth_required = bool(auth.AUTH_PASSWORD) or (n_users or 0) > 0 or not auth.DEV_MODE
    status = 200 if db_ok else 503
    return JSONResponse(status_code=status, content={
        "ok": db_ok, "service": "biotorf-comms", "version": app.version,
        "db": ("postgres: " + ("up" if db_ok else "DOWN — " + db_msg))
              if store.IS_POSTGRES else "sqlite",
        "ts": now_iso(),
        # authRequired: фронт показывает экран входа; hasUsers — что на нём
        # предложить «зарегистрировать первого сотрудника (гендиректора)»
        "authRequired": auth_required,
        "hasUsers": (n_users or 0) > 0,
        "devMode": bool(auth.DEV_MODE)})


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


def _tg_media_label(msg: dict) -> str:
    """Подпись для нетекстовых сообщений (голос, фото, видео, документ...),
    чтобы входящее не терялось в ленте как пустая строка."""
    if msg.get("voice"):
        return "🎤 Голосовое сообщение"
    if msg.get("audio"):
        return "🎵 Аудио"
    if msg.get("photo"):
        return "🖼 Фото"
    if msg.get("video_note"):
        return "⭕ Видео-кружок"
    if msg.get("video"):
        return "📹 Видео"
    if msg.get("document"):
        return "📎 Документ"
    if msg.get("sticker"):
        return "[стикер]"
    if msg.get("contact"):
        return "[анкета: контакт]"
    if msg.get("location"):
        return "[геолокация]"
    return ""


TG_MEDIA_MAX_BYTES = 20 * 1024 * 1024  # 20 МБ на файл — защита от дисковых атак


def download_tg_voice(file_info: dict) -> dict | None:
    """Скачать голосовой/аудио файл из Telegram Bot API в локальное хранилище.

    file_path выдаётся getFile и действительна ~1 час; качаем сразу при приёме,
    чтобы клиент мог слушать запись в любой момент (Bot API отдаёт файлы только
    по https, special:// paths не читаются напрямую)."""
    fid = file_info.get("file_id")
    if not fid or not TELEGRAM_BOT_TOKEN:
        return None
    try:
        res = tg_api("getFile", {"file_id": fid})
        fp = (res.get("result") or {}).get("file_path")
        if not fp:
            log.warning("[tg-media] getFile не вернул file_path для %s…", fid[:24])
            return None
        url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{fp}"
        with _open(url, max(NET_TIMEOUT, 30)) as resp:
            data = resp.read(TG_MEDIA_MAX_BYTES + 1)
        if len(data) > TG_MEDIA_MAX_BYTES:
            log.warning("[tg-media] файл больше 20 МБ — пропущен")
            return None
        MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        ext = Path(fp).suffix or ".oga"
        media_id = hashlib.sha1(fid.encode()).hexdigest()[:16]
        dest = MEDIA_DIR / f"{media_id}{ext}"
        dest.write_bytes(data)
        return {
            "mediaId": media_id,
            "mimeType": file_info.get("mime_type") or "audio/ogg",
            "size": len(data),
            "duration": file_info.get("duration"),
        }
    except Exception as e:
        log.warning("[tg-media] скачивание не удалось: %s", e)
        return None


# ── вебхук: Telegram ─────────────────────────────────────────────────────────
# Присылается вашим getUpdates-воркером (или самим Telegram при direct-webhook):
# { "update_id": 123, "message": { "from": {...}, "chat": {...}, "text": "..." } }
@app.post("/webhooks/telegram")
async def telegram_webhook(
    request: Request,
    x_bot_secret: str | None = Header(None),
    x_webhook_secret: str | None = Header(None, alias="X-Webhook-Secret"),
    secret: str = Query(""),   # LEGACY: секрет в query — поддержка старых
                               # версий воркера; секреты попадают в access-логи,
                               # новый telegram_worker передаёт X-Bot-Secret в заголовке
):
    # секрет приходит либо от нашего воркера (заголовок X-Bot-Secret),
    # либо напрямую от Telegram (заголовок X-Telegram-Bot-Api-Secret-Token,
    # заданный через setWebhook) — принимаем любой из них
    provided = x_bot_secret or request.headers.get("x-telegram-bot-api-secret-token") or secret
    check_secret(provided, TELEGRAM_SECRET, "TELEGRAM_WEBHOOK_SECRET")
    payload = await request.json()
    msg = payload.get("message") or payload.get("channel_post")
    if not msg:
        return {"ignored": True, "reason": "не message-событие"}

    chat = msg.get("chat") or {}
    frm = msg.get("from") or {}
    external_id = str(payload.get("update_id") or msg.get("message_id"))

    # голосовые/аудио: скачиваем файл сразу при приёме, чтобы его можно было
    # прослушать в чате CRM (Bot API отдаёт file_path только на время)
    media = None
    for mkey in ("voice", "audio"):
        if msg.get(mkey):
            media = download_tg_voice(msg[mkey])
            if media:
                break

    item = {
        "id": new_id(),
        "kind": "telegram",
        "dir": "in",
        "contact": " ".join(filter(None, [frm.get("first_name"), frm.get("last_name")])) or None,
        "handle": ("@" + frm["username"]) if frm.get("username") else None,
        "phone": frm.get("phone_number") or None,
        "ts": datetime.fromtimestamp(msg.get("date", time.time()), timezone.utc).isoformat(timespec="seconds"),
        "text": msg.get("text") or msg.get("caption") or _tg_media_label(msg),
        "read": False,
        "source": "webhook:telegram",
        "externalId": external_id,
        # chatId обязателен для исходящей отправки (sendMessage) из ленты;
        # userIndex — запасной вариант, если чат ещё не был создан ботом
        "payload": {
            "chatId": chat.get("id"),
            "username": frm.get("username"),
            "userIndex": frm.get("id"),
            **({"media": media} if media else {}),
        },
    }
    item["farmId"] = (auto_link(item["phone"]) or auto_link_handle(item["handle"])
                      or crm.auto_link_tg(store.connect(), item["handle"], item["phone"]))
    saved = store.insert(item)
    # сквозная интеграция: входящее сообщение попадает в карточку клиента и
    # в историю связанного сквозного процесса (руководство §6 «История»)
    try:
        crm.register_comm(store.connect(), saved)
    except Exception as e:
        log.warning("[crm] register_comm skip: %s", e)
    return saved


def auto_link_handle(handle: str | None) -> str | None:
    """Привязка входящего Telegram-сообщения к клиенту по @username.

    Если у клиента в реестре (farms.json) заполнено поле telegram — сообщение
    сразу попадает в карточку клиента, даже без номера телефона. Кэш/индекс —
    farms_index (перечитывает файл только при изменении mtime)."""
    return farms_index.link_by_handle(FARMS_FILE, handle)


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
                item["farmId"] = auto_link(item["phone"]) \
                    or crm.auto_link_tg(store.connect(), None, item["phone"])
                saved = store.insert(item)
                try:
                    crm.register_comm(store.connect(), saved)
                except Exception as e:
                    log.warning("[crm] register_comm skip: %s", e)
                created.append(saved)
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
async def telephony_webhook(
    request: Request,
    token: str = Query(""),   # LEGACY: токен в query (некоторые ATS умеют только URL);
                              # предпочтительно передавать тот же секрет в заголовке
                              # X-Webhook-Secret — query попадает в access-логи
    x_webhook_secret: str | None = Header(None, alias="X-Webhook-Secret"),
):
    check_secret(x_webhook_secret or token, TELEPHONY_TOKEN, "TELEPHONY_TOKEN")
    payload = await request.json()
    calls = payload if isinstance(payload, list) else payload.get("calls", [payload])
    created = []
    for c in calls:
        item = normalize_cdr(c)
        item["farmId"] = auto_link(item["phone"]) \
            or crm.auto_link_tg(store.connect(), None, item["phone"])
        saved = store.insert(item)
        try:
            crm.register_comm(store.connect(), saved)
        except Exception as e:
            log.warning("[crm] register_comm skip: %s", e)
        created.append(saved)
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

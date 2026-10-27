"""Авторизация и RBAC для BIOTORF Comms API.

  • POST /auth/register     — регистрация сотрудника с фронтенда; ПЕРВЫЙ
    аккаунт автоматически получает роль «director» (генеральный директор),
    остальные — «pending» без прав, пока директор не выдаст роль;
  • POST /auth/login        — обмен логина/пароля сотрудника на JWT
    (HS256, stdlib hmac/hashlib — без внешних зависимостей); если таблица
    users пуста, допускается прежний режим общего пароля AUTH_PASSWORD;
  • каждый запрос /api/*    требует заголовок Authorization: Bearer <token>;
  • роль в токене ограничивает права на сервере (см. ROLE_PERMS): запись/
    удаление доступны только ролям с нужным правом, «read-only» роли
    (agronomist/production/logistics/marketing) не могут менять чужие данные;
  • выдача ролей сотрудникам — эксклюзивное право роли director
    (PUT /api/users/{login}/role, см. main.py + backend/users.py);
  • /health, /docs, /openapi.json и /webhooks/* остаются без токена —
    вебхуки защищаются секретами/подписями (как раньше), health нужен
    docker-проверкам и экрану входа фронта.

Пароль задаётся переменной AUTH_PASSWORD (в Docker — из .env). Если он пуст
и сотрудников ещё нет, включается DEV_MODE: локальная разработка работает
как раньше (любой токен принимается с ролью director). В проде при пустом
пароле и пустой таблице users включается LOCKED режим: все /api/* отвечают
503, пока первый сотрудник не зарегистрируется через фронтенд.
"""

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time

# ── конфигурация ─────────────────────────────────────────────────────────────
AUTH_SECRET = os.environ.get("AUTH_SECRET", "").strip()
AUTH_PASSWORD = os.environ.get("AUTH_PASSWORD", "").strip()
AUTH_TOKEN_TTL = int(os.environ.get("AUTH_TOKEN_TTL", "43200") or 43200)  # 12 ч
DEV_MODE = os.environ.get("DEV_MODE", "").strip().lower() in ("1", "true", "yes", "on")

ROLES = {
    "director": "Генеральный директор",
    "operations": "Операционный руководитель",
    "sales_head": "Руководитель продаж",
    "dispatcher": "CRM-диспетчер",
    "sales": "Менеджер продаж",
    "agronomist": "Агроном",
    "production": "Производство",
    "warehouse": "Склад",
    "logistics": "Логистика",
    "finance": "Финансы",
    "marketing": "Маркетинг",
}

# Права на запись по разделам (серверная версия EDIT_RULES фронтенда).
ROLE_PERMS = {
    # реестр сотрудников: писать (выдавать/снимать роли, удалять) — только
    # генеральный директор; смотреть список могут все авторизованные
    "users": {"director"},
    "crm": {"director", "operations", "sales_head", "dispatcher", "sales"},
    "comms": {"director", "operations", "sales_head", "dispatcher", "sales",
              "agronomist", "marketing"},
    "orders": {"director", "operations", "sales_head", "sales", "finance"},
    "shipments": {"director", "operations", "logistics"},
    "tasks": set(ROLES),
    "admin": {"director", "operations"},   # seed/reset/dev-инструменты
}

# ── JWT (HS256, минимальная реализация на stdlib) ────────────────────────────
def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64ud(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sign(secret: bytes, msg: bytes) -> bytes:
    return hmac.new(secret, msg, hashlib.sha256).digest()


def make_token(user: str, role: str, ttl: int | None = None,
               token_version: int = 0) -> str:
    secret = (AUTH_SECRET or AUTH_PASSWORD or "dev-insecure-secret").encode()
    header = _b64u(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = _b64u(json.dumps({
        "sub": user, "role": role if role in ROLES else "sales",
        "iat": int(time.time()), "exp": int(time.time()) + (ttl or AUTH_TOKEN_TTL),
        "tv": int(token_version or 0),
    }).encode())
    sig = _b64u(_sign(secret, f"{header}.{body}".encode()))
    return f"{header}.{body}.{sig}"


def verify_token(token: str) -> dict | None:
    """Вернуть payload токена или None (подпись не бьётся / срок истёк)."""
    try:
        h, b, s = token.split(".")
        secret = (AUTH_SECRET or AUTH_PASSWORD or "dev-insecure-secret").encode()
        expected = _b64u(_sign(secret, f"{h}.{b}".encode()))
        if not hmac.compare_digest(expected, s):
            return None
        payload = json.loads(_b64ud(b))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        if payload.get("role") not in ROLES:
            return None
        payload.setdefault("tv", 0)
        return payload
    except Exception:
        return None


# ── проверка логина ──────────────────────────────────────────────────────────
def check_password(password: str) -> bool:
    if not AUTH_PASSWORD:
        return False
    return hmac.compare_digest(password or "", AUTH_PASSWORD)


NAME_RE = re.compile(r"^[\w\-. ]{2,64}$", re.UNICODE)


def login(user: str, password: str) -> dict | None:
    """Успешный вход → {token, user, role, roleName}; неверный пароль → None."""
    user = (user or "").strip()[:64]
    if not NAME_RE.match(user):
        return None
    if not check_password(password):
        return None
    role = (os.environ.get("AUTH_DEFAULT_ROLE") or "director").strip()
    if role not in ROLES:
        role = "director"
    return {"token": make_token(user, role), "user": user, "role": role,
            "roleName": ROLES[role], "roles": ROLES,
            "expiresIn": AUTH_TOKEN_TTL}


# ── RBAC ─────────────────────────────────────────────────────────────────────
WRITE_ROUTES = (
    ("/api/crm/", "crm"),
    ("/api/comms", "comms"),
    ("/api/chat/", "comms"),
    ("/api/media", "comms"),
    ("/api/logistics", "shipments"),
    ("/api/dev/", "admin"),
    ("/api/users", "users"),      # выдача ролей; право — только у director
)


def section_for(path: str) -> str | None:
    for prefix, sec in WRITE_ROUTES:
        if path.startswith(prefix):
            return sec
    return None


def can_write(role: str, section: str) -> bool:
    return role in ROLE_PERMS.get(section, set())


def new_worker_secret() -> str:
    return secrets.token_urlsafe(32)

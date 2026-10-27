"""Реестр каналов коммуникаций и подключённых аккаунтов CRM.

Раньше каналы (telegram/whatsapp/телефония) были зашиты в код и CHECK-ограничении
таблицы comms, а привязка аккаунтов шла через farms.json / env-переменные.
Теперь:
  * каналы расширяемы — новые (instagram, facebook, vk, avito, email…) добавляются
    как строки таблицы channels либо через generic-вебхук POST /api/comms;
  * аккаунты подключаются из UI («Настройки → Каналы»): токен/секрет хранится в
    SQLite, при отдаче наружу маскируется;
  * бэкенд не пускает в comms неизвестный kind — список берётся из этого реестра.
"""

import json
import os
import re
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# Путь к SQLite — только legacy-режим (DB_BACKEND=sqlite); по умолчанию — PostgreSQL.
DB_PATH = Path(os.environ.get("DB_PATH", str(Path(__file__).resolve().parent / "comms.db")))


def _is_postgres() -> bool:
    b = (os.environ.get("DB_BACKEND") or "").strip().lower()
    if b in ("sqlite", "sqlite3"):
        return False
    if b in ("postgres", "postgresql", "pg"):
        return True
    return bool(os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_HOST"))


IS_POSTGRES = _is_postgres()

KIND_RE = re.compile(r"^[a-z0-9_]{2,24}$")

# id -> мета: как отображать, что умеет, есть ли «живой» коннектор на сервере
BUILTIN = {
    "call":      {"label": "Телефония",   "icon": "📞", "color": "#e5484d", "directions": ["in", "out"], "connectors": ["webhook", "sip"]},
    "telegram":  {"label": "Telegram",    "icon": "✈️", "color": "#2aabee", "directions": ["in", "out"], "connectors": ["bot-token"]},
    "whatsapp":  {"label": "WhatsApp",    "icon": "💬", "color": "#25d366", "directions": ["in", "out"], "connectors": ["cloud-api"]},
}

DEFAULT_CHANNELS = [
    {"id": "call", "group": "Клиентские каналы"},
    {"id": "telegram", "group": "Мессенджеры"},
    {"id": "whatsapp", "group": "Мессенджеры"},
]

# пресеты для кнопки «Добавить канал» — пользователю не нужно ничего придумывать
CHANNEL_PRESETS = [
    {"id": "instagram",  "label": "Instagram",  "icon": "📸", "color": "#c13584", "group": "Соцсети",     "directions": ["in", "out"], "connectors": ["generic-webhook", "dm-api"]},
    {"id": "facebook",   "label": "Facebook",   "icon": "📘", "color": "#1877f2", "group": "Соцсети",     "directions": ["in", "out"], "connectors": ["generic-webhook", "messenger-api"]},
    {"id": "vk",         "label": "ВКонтакте",  "icon": "🔵", "color": "#0077ff", "group": "Соцсети",     "directions": ["in", "out"], "connectors": ["generic-webhook", "vk-api"]},
    {"id": "ok",         "label": "Одноклассники", "icon": "🟠", "color": "#ee8208", "group": "Соцсети",  "directions": ["in", "out"], "connectors": ["generic-webhook"]},
    {"id": "avito",      "label": "Авито",      "icon": "🟩", "color": "#00aaff", "group": "Площадки",    "directions": ["in", "out"], "connectors": ["generic-webhook"]},
    {"id": "youdo",      "label": "YouDo",      "icon": "✅", "color": "#ff8b00", "group": "Площадки",    "directions": ["in", "out"], "connectors": ["generic-webhook"]},
    {"id": "email",      "label": "Email",      "icon": "✉️", "color": "#6e56cf", "group": "Клиентские каналы", "directions": ["in", "out"], "connecters": [], "connectors": ["smtp-imap"]},
]


def _conn():
    if IS_POSTGRES:
        import pg
        return pg.connect()
    conn = sqlite3.connect(str(DB_PATH), timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS channels (
    id          TEXT PRIMARY KEY,
    label       TEXT NOT NULL,
    icon        TEXT NOT NULL DEFAULT '🔗',
    color       TEXT NOT NULL DEFAULT '#888',
    grp         TEXT NOT NULL DEFAULT 'Прочее',
    enabled     INTEGER NOT NULL DEFAULT 1,
    directions  TEXT NOT NULL DEFAULT '["in","out"]',
    connectors  TEXT NOT NULL DEFAULT '[]',
    meta        TEXT
);
CREATE TABLE IF NOT EXISTS channel_accounts (
    id           TEXT PRIMARY KEY,
    channel      TEXT NOT NULL,
    login        TEXT NOT NULL DEFAULT '',
    display_name TEXT NOT NULL DEFAULT '',
    farm_id      TEXT,
    token        TEXT,
    secret       TEXT,
    status       TEXT NOT NULL DEFAULT 'active',
    created_by   TEXT,
    created_at   TEXT,
    updated_at   TEXT,
    UNIQUE (channel, login)
);
"""


def ensure_schema():
    with _conn() as conn:
        if IS_POSTGRES:
            # полная схема (включая channels/channel_accounts) применяется из
            # schema.sql в db._ensure_schema — здесь только seed, если пусто.
            pass
        else:
            conn.executescript(SCHEMA)
        n = conn.execute("SELECT COUNT(*) c FROM channels").fetchone()["c"]
        if n == 0:
            for ch in DEFAULT_CHANNELS:
                meta = BUILTIN.get(ch["id"], {})
                conn.execute(
                    "INSERT INTO channels (id,label,icon,color,grp,enabled,directions,connectors) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (ch["id"], meta.get("label", ch["id"]), meta.get("icon", "🔗"),
                     meta.get("color", "#888"), ch["group"], 1,
                     json.dumps(meta.get("directions", ["in", "out"])),
                     json.dumps(meta.get("connectors", []))),
                )


def valid_kind(kind: str | None) -> bool:
    """Разрешён ли kind в comms (только включённые каналы реестра)."""
    if not kind:
        return False
    with _conn() as conn:
        r = conn.execute("SELECT enabled FROM channels WHERE id=?", (kind,)).fetchone()
    return bool(r and r["enabled"])


def all_kinds() -> list[str]:
    with _conn() as conn:
        return [r["id"] for r in conn.execute("SELECT id FROM channels")]


def list_channels(include_disabled=True):
    with _conn() as conn:
        sql = "SELECT * FROM channels"
        if not include_disabled:
            sql += " WHERE enabled=1"
        rows = conn.execute(sql + " ORDER BY grp, label").fetchall()
    out = []
    for r in rows:
        acc = _accounts_for(conn_safe=None, channel=r["id"])
        out.append({
            "id": r["id"], "label": r["label"], "icon": r["icon"], "color": r["color"],
            "group": r["grp"], "enabled": bool(r["enabled"]),
            "directions": json.loads(r["directions"]), "connectors": json.loads(r["connectors"]),
            "connected": len(acc) > 0, "accounts": acc,
        })
    return out


def _accounts_for(channel: str, conn_safe=None) -> list[dict]:
    conn = conn_safe or _conn()
    own = conn_safe is None
    try:
        rows = conn.execute(
            "SELECT * FROM channel_accounts WHERE channel=? ORDER BY created_at", (channel,)
        ).fetchall()
        return [_mask(r) for r in rows]
    finally:
        if own:
            conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _mask(row) -> dict:
    """Наружу — без секретов, только маска токена."""
    tok = row["token"] or ""
    mask = (tok[:3] + "…" + tok[-2:]) if len(tok) > 8 else ("•" * len(tok) if tok else "")
    return {
        "id": row["id"], "channel": row["channel"], "login": row["login"],
        "displayName": row["display_name"], "farmId": row["farm_id"],
        "hasSecret": bool(row["secret"]), "tokenMask": mask,
        "status": row["status"], "createdAt": row["created_at"], "updatedAt": row["updated_at"],
    }


def add_channel(kind: str, data: dict) -> dict:
    kind = (kind or "").strip().lower()
    if not KIND_RE.match(kind):
        raise ValueError("Некорректный идентификатор канала (a-z0-9_, 2–24)")
    with _conn() as conn:
        if conn.execute("SELECT 1 FROM channels WHERE id=?", (kind,)).fetchone():
            raise KeyError("Канал уже существует")
        conn.execute(
            "INSERT INTO channels (id,label,icon,color,grp,enabled,directions,connectors,meta) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (kind, data.get("label", kind), data.get("icon", "🔗"), data.get("color", "#888"),
             data.get("group", "Прочее"), 1,
             json.dumps(data.get("directions", ["in", "out"])),
             json.dumps(data.get("connectors", [])), data.get("meta")),
        )
    return get_channel(kind)


def patch_channel(kind: str, data: dict) -> dict:
    fields = {k: v for k, v in {
        "label": data.get("label"), "icon": data.get("icon"), "color": data.get("color"),
        "grp": data.get("group"), "enabled": data.get("enabled"),
    }.items() if v is not None}
    # PostgreSQL-столбец enabled — INTEGER: Python bool иначе падает с
    # DatatypeMismatch ("column enabled is of type integer but expression
    # is of type boolean")
    if isinstance(fields.get("enabled"), bool):
        fields["enabled"] = int(fields["enabled"])
    sets = ", ".join(f"{k}=?" for k in fields)
    with _conn() as conn:
        if not conn.execute("SELECT 1 FROM channels WHERE id=?", (kind,)).fetchone():
            raise KeyError("Канал не найден")
        if sets:
            conn.execute(f"UPDATE channels SET {sets} WHERE id=?", (*fields.values(), kind))
    return get_channel(kind)


def get_channel(kind: str) -> dict:
    with _conn() as conn:
        r = conn.execute("SELECT * FROM channels WHERE id=?", (kind,)).fetchone()
        if not r:
            raise KeyError("Канал не найден")
        return {
            "id": r["id"], "label": r["label"], "icon": r["icon"], "color": r["color"],
            "group": r["grp"], "enabled": bool(r["enabled"]),
            "directions": json.loads(r["directions"]), "connectors": json.loads(r["connectors"]),
            "accounts": [_mask(x) for x in conn.execute(
                "SELECT * FROM channel_accounts WHERE channel=? ORDER BY created_at", (kind,))],
        }


def connect_account(kind: str, data: dict, who: str = "") -> dict:
    """Подключить аккаунт канала (токены/секреты храним в БД, наружу — маска)."""
    if kind not in all_kinds():
        raise KeyError("Неизвестный канал")
    login = (data.get("login") or "").strip()
    token = (data.get("token") or "").strip()
    secret = (data.get("secret") or "").strip()
    if kind == "telegram" and not re.match(r"^\d{6,12}:[\w-]{20,}$", token or ""):
        raise ValueError("Формат токена Telegram: 1234567:AA...")
    aid = secrets.token_hex(8)
    now = _now()
    with _conn() as conn:
        conn.execute(
            "INSERT INTO channel_accounts (id,channel,login,display_name,farm_id,token,secret,status,created_by,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (aid, kind, login, data.get("displayName") or login or kind,
             data.get("farmId"), token or None, secret or None,
             data.get("status", "active"), who, now, now),
        )
        r = conn.execute("SELECT * FROM channel_accounts WHERE id=?", (aid,)).fetchone()
    return _mask(r)


def update_account(account_id: str, data: dict) -> dict:
    fields = {}
    for src, col in (("login", "login"), ("displayName", "display_name"),
                     ("farmId", "farm_id"), ("status", "status")):
        if src in data and data[src] is not None:
            fields[col] = data[src]
    if (data.get("token") or "").strip():
        fields["token"] = data["token"].strip()
    if (data.get("secret") or "").strip():
        fields["secret"] = data["secret"].strip()
    sets = ", ".join(f"{k}=?" for k in fields)
    with _conn() as conn:
        if not conn.execute("SELECT 1 FROM channel_accounts WHERE id=?", (account_id,)).fetchone():
            raise KeyError("Аккаунт не найден")
        if sets:
            conn.execute(f"UPDATE channel_accounts SET {sets}, updated_at=? WHERE id=?",
                         (*fields.values(), _now(), account_id))
        r = conn.execute("SELECT * FROM channel_accounts WHERE id=?", (account_id,)).fetchone()
    return _mask(r)


def delete_account(account_id: str) -> None:
    with _conn() as conn:
        cur = conn.execute("DELETE FROM channel_accounts WHERE id=?", (account_id,))
        if cur.rowcount == 0:
            raise KeyError("Аккаунт не найден")


def get_secret(kind: str, field: str = "token") -> str | None:
    """Секрет активного аккаунта канала — для воркеров отправки."""
    col = "token" if field == "token" else "secret"
    with _conn() as conn:
        r = conn.execute(
            f"SELECT {col} v FROM channel_accounts WHERE channel=? AND status='active' "
            f"AND {col} IS NOT NULL ORDER BY updated_at DESC LIMIT 1", (kind,)).fetchone()
    return r["v"] if r else None

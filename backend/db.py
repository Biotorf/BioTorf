"""Простейкое хранилище коммуникаций: SQLite (файл comms.db рядом с backend/).

Таблица comms полностью повторяет модель фронтенда (stores/db.js / CommsView.vue):
  kind     : call | telegram | whatsapp
  dir      : in | out
  farmId   : привязка к хозяйству (может быть NULL — непривязанные)
  contact  : имя контакта
  phone    : номер телефона (звонки, WhatsApp)
  handle   : telegram-username (сообщения Telegram)
  ts       : ISO-8601 timestamp
  duration : длительность звонка в секундах
  status   : Разговор | Пропущенный
  text     : текст сообщения
  note     : резюме звонка
  read     : 0/1
  source   : manual | demo | webhook:telegram | webhook:whatsapp | webhook:telephony
"""

import json
import os
import re
import sqlite3
from pathlib import Path

# Путь к БД переопределяется через DB_PATH (в Docker — /data/comms.db на volume)
DB_PATH = Path(os.environ.get("DB_PATH", str(Path(__file__).resolve().parent / "comms.db")))

SCHEMA = """
CREATE TABLE IF NOT EXISTS comms (
    id         TEXT PRIMARY KEY,
    kind       TEXT NOT NULL CHECK (kind IN ('call','telegram','whatsapp')),
    dir        TEXT NOT NULL DEFAULT 'in' CHECK (dir IN ('in','out')),
    farm_id    TEXT,
    contact    TEXT,
    phone      TEXT,
    handle     TEXT,
    ts         TEXT NOT NULL,
    duration   INTEGER NOT NULL DEFAULT 0,
    status     TEXT,
    text       TEXT,
    note       TEXT,
    read       INTEGER NOT NULL DEFAULT 0,
    source     TEXT NOT NULL DEFAULT 'manual',
    external_id TEXT,
    payload    TEXT,
    peer_key   TEXT
);
CREATE INDEX IF NOT EXISTS idx_comms_ts      ON comms (ts DESC);
CREATE INDEX IF NOT EXISTS idx_comms_farm    ON comms (farm_id);
CREATE INDEX IF NOT EXISTS idx_comms_unread  ON comms (read);

CREATE UNIQUE INDEX IF NOT EXISTS idx_comms_ext ON comms (source, external_id)
    WHERE external_id IS NOT NULL;
CREATE TABLE IF NOT EXISTS chat_drafts (
    peer_key TEXT PRIMARY KEY,
    draft    TEXT NOT NULL DEFAULT '',
    updated  TEXT NOT NULL
);
"""

FIELDS = [
    "id", "kind", "dir", "farmId", "contact", "phone", "handle",
    "ts", "duration", "status", "text", "note", "read", "source",
    "externalId", "payload", "peerKey",
]


def compute_peer_key(item: dict) -> str | None:
    """Ключ чата для мессенджер-ленты: диалог с собеседником идентифицируется
    телефоном (WhatsApp/звонки), telegram-username, иначе chatId/userIndex."""
    d = digits_for_key(item.get("phone"))
    if len(d) >= 6:
        return "tel:" + d
    h = (item.get("handle") or "").lstrip("@").lower()
    if h:
        return "tg:" + h
    pl = item.get("payload") or {}
    pid = pl.get("chatId") or pl.get("userIndex")
    return f"tgid:{pid}" if pid else None


def digits_for_key(s) -> str:
    import re as _re
    d = _re.sub(r"\D", "", s or "")
    # нормализация кыргызских/узбекских номеров: 0XX XXX XX XX <-> +996XXXXXXXXX
    if d.startswith("996") and len(d) == 12:
        return d[3:]
    if d.startswith("998") and len(d) == 12:
        return d[3:]
    if len(d) == 11 and d.startswith("0"):
        return d[1:]
    if len(d) == 10 and d[:3] in ("505","555","700","701","702","707","770","771","772","777","880","999","312"):
        return d
    return d[-9:] if len(d) >= 6 else d


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    # WAL: читатели не блокируются писателем и наоборот — критично при
    # одновременной работе API (несколько сотрудников + webhook-штормы) и
    # telegram_worker'а с одной базой. journal_mode персистентен в файле БД,
    # sync=NORMAL ускоряет запись, сохраняя согласованность при WAL.
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=15000")
    except sqlite3.Error:
        pass  # старые/закрытые БД без поддержки WAL остаются на DELETE-journal
    return conn


def _ensure_schema(conn) -> None:
    """Создать схему; для старых БД — миграция: добавить колонку peer_key."""
    has_table = conn.execute(
        "SELECT name FROM sqlite_master WHERE name='comms'").fetchone()
    if has_table:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(comms)")}
        if "peer_key" not in cols:
            conn.execute("ALTER TABLE comms ADD COLUMN peer_key TEXT")
    conn.executescript(SCHEMA)


def init_db() -> None:
    with connect() as conn:
        _ensure_schema(conn)
        # разово проставляем peer_key историческим записям, у которых он пуст
        rows = conn.execute(
            "SELECT * FROM comms WHERE peer_key IS NULL OR peer_key=''").fetchall()
        for r in rows:
            pk = compute_peer_key(to_dict(r))
            if pk:
                conn.execute("UPDATE comms SET peer_key=? WHERE id=?", (pk, r["id"]))


def to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    return {
        "id": d["id"],
        "kind": d["kind"],
        "dir": d["dir"],
        "farmId": d["farm_id"],
        "contact": d["contact"],
        "phone": d["phone"],
        "handle": d["handle"],
        "ts": d["ts"],
        "duration": d["duration"],
        "status": d["status"],
        "text": d["text"],
        "note": d["note"],
        "read": bool(d["read"]),
        "source": d["source"],
        "externalId": d["external_id"],
        "payload": json.loads(d["payload"]) if d["payload"] else None,
        "peerKey": d.get("peer_key"),
    }


COL_MAP = {
    "farmId": "farm_id",
    "externalId": "external_id",
    "peerKey": "peer_key",
}


def insert(item: dict) -> dict:
    if "peerKey" not in item or not item.get("peerKey"):
        pk = compute_peer_key(item)
        if pk:
            item = {**item, "peerKey": pk}
    cols, vals = [], []
    for f in FIELDS:
        if f in item and item[f] is not None:
            cols.append(COL_MAP.get(f, f))
            v = item[f]
            if f == "read":
                v = int(bool(v))
            elif f == "payload":
                v = json.dumps(v, ensure_ascii=False)
            vals.append(v)
    sql = (
        f"INSERT OR IGNORE INTO comms ({', '.join(cols)}) "
        f"VALUES ({', '.join('?' for _ in cols)})"
    )
    with connect() as conn:
        cur = conn.execute(sql, vals)
        if cur.rowcount == 0:
            # дубликат webhook-события — возвращаем существующую запись
            row = conn.execute(
                "SELECT * FROM comms WHERE source=? AND external_id=?",
                (item.get("source"), item.get("externalId")),
            ).fetchone()
            return to_dict(row)
        row = conn.execute("SELECT * FROM comms WHERE id=?", (item["id"],)).fetchone()
        return to_dict(row)


def get(comm_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM comms WHERE id=?", (comm_id,)).fetchone()
        return to_dict(row) if row else None


def list_comms(kind=None, farm_id=None, unread_only=False, limit=200, offset=0):
    where, params = [], []
    if kind:
        where.append("kind = ?")
        params.append(kind)
    if farm_id:
        where.append("farm_id = ?")
        params.append(farm_id)
    if unread_only:
        where.append("read = 0")
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    sql = f"SELECT * FROM comms {clause} ORDER BY ts DESC LIMIT ? OFFSET ?"
    params += [limit, offset]
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
        total = conn.execute(f"SELECT COUNT(*) c FROM comms {clause}", params[:-2]).fetchone()["c"]
        return [to_dict(r) for r in rows], total


def update(comm_id: str, patch: dict) -> dict | None:
    allowed = {"farmId": "farm_id", "read": "read", "note": "note",
               "status": "status", "contact": "contact", "phone": "phone",
               "handle": "handle", "text": "text", "payload": "payload"}
    sets, params = [], []
    for k, col in allowed.items():
        if k in patch:
            sets.append(f"{col} = ?")
            v = patch[k]
            if col == "read":
                v = int(bool(v))
            elif col == "payload":
                v = json.dumps(v, ensure_ascii=False)
            params.append(v)
    if not sets:
        return get(comm_id)
    params.append(comm_id)
    with connect() as conn:
        conn.execute(f"UPDATE comms SET {', '.join(sets)} WHERE id = ?", params)
        # привязка к клиенту распространяется на весь чат (как в мессенджер-CRM:
        # диалог целиком принадлежит одному хозяйству)
        if "farmId" in patch and patch["farmId"]:
            row = conn.execute("SELECT peer_key FROM comms WHERE id=?", (comm_id,)).fetchone()
            if row and row["peer_key"]:
                conn.execute(
                    "UPDATE comms SET farm_id=? WHERE peer_key=? AND farm_id IS NULL",
                    (patch["farmId"], row["peer_key"]))
    return get(comm_id)


def mark_all_read() -> int:
    with connect() as conn:
        cur = conn.execute("UPDATE comms SET read = 1 WHERE read = 0")
        return cur.rowcount


def pending_outbox(kind: str, limit: int = 20) -> list[dict]:
    """Исходящие ответы, ещё не доставленные в Telegram (статус «В очереди»)."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM comms WHERE kind=? AND dir='out' AND status='В очереди' "
            "ORDER BY ts ASC LIMIT ?",
            (kind, limit),
        ).fetchall()
        return [to_dict(r) for r in rows]


def delete(comm_id: str) -> bool:
    with connect() as conn:
        cur = conn.execute("DELETE FROM comms WHERE id = ?", (comm_id,))
        return cur.rowcount > 0


def chats(limit: int = 200) -> list[dict]:
    """Собрать чаты — группировка сообщений по собеседнику, как в мессенджере.

    Возвращает список диалогов: identity (клиент/контакт/телефон/ник), канал,
    счётчик непрочитанных, последние сообщения и черновик ответа."""
    with connect() as conn:
        peers = conn.execute(
            "SELECT peer_key, MAX(ts) last_ts, COUNT(*) c FROM comms "
            "WHERE peer_key IS NOT NULL GROUP BY peer_key "
            "ORDER BY last_ts DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for pr in peers:
            msgs_rows = conn.execute(
                "SELECT rowid, * FROM comms WHERE peer_key=? ORDER BY ts ASC, rowid ASC",
                (pr["peer_key"],)).fetchall()
            msgs = []
            for r in msgs_rows:
                d = to_dict(r)
                d["seq"] = r["rowid"]
                msgs.append(d)
            g = {
                "key": pr["peer_key"],
                "kind": "call",
                "farmId": None,
                "contact": None,
                "phone": None,
                "handle": None,
                "chatId": None,
                "messages": msgs,
                "unread": 0,
                "lastTs": pr["last_ts"],
                "total": len(msgs),
            }
            for m in msgs:
                if m["kind"] != "call":
                    g["kind"] = m["kind"]          # канал берём из сообщений-диалога
                if m.get("farmId"):
                    g["farmId"] = m["farmId"]
                if m.get("contact"):
                    g["contact"] = m["contact"]
                if m.get("phone"):
                    g["phone"] = m["phone"]
                if m.get("handle"):
                    g["handle"] = m["handle"]
                pl = m.get("payload") or {}
                if pl.get("chatId"):
                    g["chatId"] = pl["chatId"]
                if not m["read"] and m["dir"] == "in":
                    g["unread"] += 1
                if m["dir"] == "out" and m.get("status"):
                    g["lastOutStatus"] = m["status"]
            g["lastMessage"] = msgs[-1] if msgs else None
            dr = conn.execute(
                "SELECT draft FROM chat_drafts WHERE peer_key=?", (pr["peer_key"],)).fetchone()
            g["draft"] = (dr["draft"] if dr else "") or ""
            out.append(g)
        return out


def mark_peer_read(peer_key: str) -> int:
    """Отметить прочитанными все входящие конкретного чата."""
    with connect() as conn:
        cur = conn.execute(
            "UPDATE comms SET read=1 WHERE peer_key=? AND read=0 AND dir='in'",
            (peer_key,))
        return cur.rowcount


def save_draft(peer_key: str, draft: str, ts: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO chat_drafts (peer_key, draft, updated) VALUES (?,?,?) "
            "ON CONFLICT(peer_key) DO UPDATE SET draft=excluded.draft, updated=excluded.updated",
            (peer_key, draft, ts))


def stats():
    with connect() as conn:
        by_kind = {r["kind"]: r["c"] for r in conn.execute(
            "SELECT kind, COUNT(*) c FROM comms GROUP BY kind")}
        unread = conn.execute("SELECT COUNT(*) c FROM comms WHERE read=0").fetchone()["c"]
        calls_in = conn.execute(
            "SELECT COUNT(*) c FROM comms WHERE kind='call' AND dir='in'").fetchone()["c"]
        calls_out = conn.execute(
            "SELECT COUNT(*) c FROM comms WHERE kind='call' AND dir='out'").fetchone()["c"]
        missed = conn.execute(
            "SELECT COUNT(*) c FROM comms WHERE kind='call' AND status='Пропущенный'").fetchone()["c"]
        unlinked = conn.execute(
            "SELECT COUNT(*) c FROM comms WHERE farm_id IS NULL").fetchone()["c"]
    return {
        "total": sum(by_kind.values()),
        "byKind": by_kind,
        "unread": unread,
        "callsIn": calls_in,
        "callsOut": calls_out,
        "missedCalls": missed,
        "unlinked": unlinked,
    }

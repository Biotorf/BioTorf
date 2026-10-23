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
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "comms.db"

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
    payload    TEXT
);
CREATE INDEX IF NOT EXISTS idx_comms_ts      ON comms (ts DESC);
CREATE INDEX IF NOT EXISTS idx_comms_farm    ON comms (farm_id);
CREATE INDEX IF NOT EXISTS idx_comms_unread  ON comms (read);
CREATE UNIQUE INDEX IF NOT EXISTS idx_comms_ext ON comms (source, external_id)
    WHERE external_id IS NOT NULL;
"""

FIELDS = [
    "id", "kind", "dir", "farmId", "contact", "phone", "handle",
    "ts", "duration", "status", "text", "note", "read", "source",
    "externalId", "payload",
]


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


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
    }


COL_MAP = {
    "farmId": "farm_id",
    "externalId": "external_id",
}


def insert(item: dict) -> dict:
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
               "handle": "handle", "text": "text"}
    sets, params = [], []
    for k, col in allowed.items():
        if k in patch:
            sets.append(f"{col} = ?")
            v = patch[k]
            if col == "read":
                v = int(bool(v))
            params.append(v)
    if not sets:
        return get(comm_id)
    params.append(comm_id)
    with connect() as conn:
        conn.execute(f"UPDATE comms SET {', '.join(sets)} WHERE id = ?", params)
    return get(comm_id)


def mark_all_read() -> int:
    with connect() as conn:
        cur = conn.execute("UPDATE comms SET read = 1 WHERE read = 0")
        return cur.rowcount


def delete(comm_id: str) -> bool:
    with connect() as conn:
        cur = conn.execute("DELETE FROM comms WHERE id = ?", (comm_id,))
        return cur.rowcount > 0


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

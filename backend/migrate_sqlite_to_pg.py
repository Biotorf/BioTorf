"""Однократная миграция данных SQLite → PostgreSQL.

Использование (из каталога backend/):
    python migrate_sqlite_to_pg.py /path/to/comms.db

Требования: psycopg[binary], существующий файл SQLite (обычно /data/comms.db
из docker-volume dbdata). Скрипт идемпотентен: повторный запуск не дублирует
записи (INSERT ... ON CONFLICT DO NOTHING / DO UPDATE).

Миграция включает ручную перестройку старых sqlite-таблиц comms (CHECK по kind)
— так же, как это делал db._ensure_schema для SQLite.
"""

import os
import re
import sqlite3
import sys

# чтобы postgres-режим модулей не активировался до настройки DATABASE_URL
os.environ.pop("DB_BACKEND", None)

import db as store          # noqa: E402  (sqlite-режим)
import pg                   # noqa: E402


TABLES = [
    # (table, columns, conflict_cols, update_on_conflict)
    ("comms", ["id", "kind", "dir", "farm_id", "contact", "phone", "handle",
               "ts", "duration", "status", "text", "note", "read", "source",
               "external_id", "payload", "peer_key"], ["id"], True),
    ("chat_drafts", ["peer_key", "draft", "updated"], ["peer_key"], True),
    ("channels", ["id", "label", "icon", "color", "grp", "enabled",
                  "directions", "connectors", "meta"], ["id"], False),
    ("channel_accounts", ["id", "channel", "login", "display_name", "farm_id",
                          "token", "secret", "status", "created_by",
                          "created_at", "updated_at"], ["id"], False),
    ("crm_records", ["id", "coll", "data", "updated"], ["coll", "id"], True),
    ("logistics_docs", ["id", "kind", "data", "updated"], ["id"], True),
    ("users", ["login", "name", "role", "pw_hash", "created_at", "active",
               "position", "phone", "email", "note", "token_version"],
     ["login"], True),
]

_COMMS_TABLE = """
CREATE TABLE comms (
    id         TEXT PRIMARY KEY,
    kind       TEXT NOT NULL,
    dir        TEXT NOT NULL DEFAULT 'in' CHECK (dir IN ('in','out')),
    farm_id    TEXT, contact TEXT, phone TEXT, handle TEXT,
    ts         TEXT NOT NULL,
    duration   INTEGER NOT NULL DEFAULT 0,
    status     TEXT, text TEXT, note TEXT,
    read       INTEGER NOT NULL DEFAULT 0,
    source     TEXT NOT NULL DEFAULT 'manual',
    external_id TEXT, payload TEXT, peer_key TEXT
);
"""


def _upgrade_legacy_sqlite(sconn):
    """То же, что db._ensure_schema делал для старых БД: добавить peer_key и
    снять CHECK(kind...) — иначе колонки может не хватать при дампе."""
    cols = {r["name"] for r in sconn.execute("PRAGMA table_info(comms)")}
    ddl = sconn.execute(
        "SELECT sql FROM sqlite_master WHERE name='comms'").fetchone()["sql"] or ""
    if "peer_key" not in cols:
        sconn.execute("ALTER TABLE comms ADD COLUMN peer_key TEXT")
        cols.add("peer_key")
    m = re.search(r"kind\s+TEXT.*?CHECK\s*\(.*?\)", ddl, re.IGNORECASE)
    if m and "telegram" in m.group(0):
        sconn.execute("ALTER TABLE comms RENAME TO comms_old")
        sconn.execute(_COMMS_TABLE)
        common = [c for c in store.FIELDS_SQL_COLS if c in cols]
        sconn.execute("INSERT INTO comms (%s) SELECT %s FROM comms_old"
                      % (", ".join(common), ", ".join(common)))
        sconn.execute("DROP TABLE comms_old")
    sconn.commit()


def main(src: str) -> None:
    if not os.path.exists(src):
        sys.exit(f"SQLite-файл не найден: {src}")
    print(f"[migrate] источник: {src}")
    print(f"[migrate] приёмник: {pg._database_url().split('@')[-1]}")

    sconn = sqlite3.connect(src)
    sconn.row_factory = sqlite3.Row
    sconn.execute("PRAGMA busy_timeout=15000")
    # таблицы comms/chat_drafts могут отсутствовать в очень старых БД
    have = {r["name"] for r in sconn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    if "comms" in have:
        _upgrade_legacy_sqlite(sconn)

    with pg.connect() as pconn:
        total = 0
        for table, cols, conf, do_update in TABLES:
            if table not in have:
                print(f"  - {table}: нет в источнике — пропущено")
                continue
            rows = sconn.execute(f"SELECT {', '.join(cols)} FROM {table}").fetchall()
            if not rows:
                print(f"  - {table}: пусто")
                continue
            ph = ", ".join("?" for _ in cols)
            sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({ph})"
            if do_update:
                upd = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c not in conf)
                sql += (f" ON CONFLICT({', '.join(conf)}) DO UPDATE SET {upd}"
                        if upd else f" ON CONFLICT({', '.join(conf)}) DO NOTHING")
            else:
                sql += f" ON CONFLICT({', '.join(conf)}) DO NOTHING"
            n = 0
            for r in rows:
                pconn.execute(sql, tuple(r[c] for c in cols))
                n += 1
            total += n
            print(f"  + {table}: {n} строк")
        # сброс счётчика seq после импорта comms (вставленные строки уже заняли
        # значения identity автоматически — пересчитывать не нужно)
        mx = pconn.execute("SELECT COALESCE(MAX(seq),0) m FROM comms").fetchone()["m"]
        print(f"[migrate] готово: {total} строк, max seq comms = {mx}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/data/comms.db")

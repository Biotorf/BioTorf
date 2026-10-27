"""Слой PostgreSQL для BIOTORF Business OS.

Модуль предоставляет DB-API-совместимую обёртку над psycopg (v3), чтобы весь
бэкенд работал на PostgreSQL без переписывания SQL:

  * плейсхолдеры "?" автоматически конвертируются в "$1, $2, ..." ;
  * курсор отдаёт строки как DictRow — доступны и по имени (row["c"]),
    и по индексу (row[0]), как в старом sqlite3.Row;
  * автокоммит после каждого execute (эмуляция поведения sqlite3 с
    isolation_level=None) + явный conn.commit() тоже безопасен;
  * executescript() — для многооператорных DDL-скриптов (схема);
  * connection_factory=db.connect — для sqlite3.dump / миграции SQLite→PG.

Подключение берётся из переменных окружения:
  DATABASE_URL  (dsn, предпочтительно) либо
  POSTGRES_HOST / POSTGRES_PORT / POSTGRES_DB / POSTGRES_USER / POSTGRES_PASSWORD
"""

import os
import re

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


def _database_url() -> str:
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if url:
        return url
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "biotorf")
    user = os.environ.get("POSTGRES_USER", "biotorf")
    pw = os.environ.get("POSTGRES_PASSWORD", "biotorf")
    return f"postgresql://{user}:{pw}@{host}:{port}/{db}"


def qmark_to_format(sql: str) -> str:
    """Конвертировать sqlite-плейсхолдеры '?' в формат psycopg '%s'.

    Символы '?' внутри строковых литералов ('...') и кавычек идентификаторов
    ("..." и `...`) не подменяются — иначе ломаются запросы с текстом в них.
    Проценты вне литералов удваиваются до '%%', чтобы psycopg (paramstyle
    pyformat) не принял их за маркер формата.
    """
    out = []
    i, ln = 0, len(sql)
    while i < ln:
        c = sql[i]
        if c == "'":                      # строковый литерал — выносим как есть
            j = i + 1
            while j < ln:
                if sql[j] == "\\" and j + 1 < ln:
                    j += 2
                    continue
                if sql[j] == "'":
                    if j + 1 < ln and sql[j + 1] == "'":  # '' — экранированная кавычка
                        j += 2
                        continue
                    break
                j += 1
            end = min(j + 1, ln)
            out.append(sql[i:end])
            i = end
        elif c in ('"', "`"):             # кавычки идентификаторов
            j = i + 1
            while j < ln and sql[j] != c:
                j += 1
            end = min(j + 1, ln)
            out.append(sql[i:end])
            i = end
        elif c == "?":
            out.append("%s")
            i += 1
        elif c == "%":
            out.append("%%")
            i += 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def split_statements(script: str):
    """Разбить SQL-скрипт на операторы по ';' (учитывая ''-кавычки)."""
    parts, buf = [], []
    i, ln = 0, len(script)
    in_str = False
    while i < ln:
        c = script[i]
        if in_str:
            buf.append(c)
            if c == "'":
                if i + 1 < ln and script[i + 1] == "'":
                    buf.append("'")
                    i += 2
                    continue
                in_str = False
            i += 1
            continue
        if c == "'":
            in_str = True
            buf.append(c)
            i += 1
            continue
        if c == "-" and script.startswith("--", i):   # комментарий до конца строки
            j = script.find("\n", i)
            i = ln if j == -1 else j
            continue
        if c == ";":
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


class Row(dict):
    """Строка результата: доступ по имени (row["col"], как sqlite3.Row) И по
    позиции (row[0] — так пишет старый код в crm.py/logistics.py)."""

    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return dict.__getitem__(self, key)


def _wrap_row(row):
    if row is None or isinstance(row, dict):
        return row
    try:
        return Row(zip(row.keys(), row))   # psycopg3 Row: dict-like + позиционный
    except Exception:
        return row


class CompatRow:
    """Обёртка строки psycopg (dict_row): доступ и по имени, и по индексу —
    как у sqlite3.Row. Нужен потому, что legacy-код местами пишет row[0]."""

    __slots__ = ("_d", "_t")

    def __init__(self, d):
        self._d = d
        self._t = tuple(d.values())

    def __getitem__(self, key):
        return self._t[key] if isinstance(key, int) else self._d[key]

    def get(self, key, default=None):
        return self._d.get(key, default)

    def keys(self):
        return self._d.keys()

    def values(self):
        return self._d.values()

    def items(self):
        return self._d.items()

    def __iter__(self):
        return iter(self._d)

    def __len__(self):
        return len(self._d)

    def __contains__(self, key):
        return key in self._d

    def __eq__(self, other):
        if isinstance(other, CompatRow):
            return self._d == other._d
        if isinstance(other, dict):
            return self._d == other
        return NotImplemented

    def __repr__(self):
        return f"CompatRow({self._d!r})"


def compat_dict_row(cursor):
    """row_factory для psycopg: dict_row + позиционный доступ."""
    from psycopg.rows import dict_row as _dr
    mapping = _dr(cursor)
    if mapping is None:
        return None
    def _f(values):
        row = mapping(values)
        return None if row is None else CompatRow(row)
    return _f


class Cursor:
    """Обёртка psycopg-cursora: '?'-плейсхолдеры + строки-словари."""

    def __init__(self, cur):
        self._cur = cur

    def execute(self, sql, params=None):
        self._cur.execute(qmark_to_format(sql), tuple(params) if params else ())
        return self

    def executemany(self, sql, seq_of_params):
        self._cur.executemany(qmark_to_format(sql),
                              [tuple(p) for p in seq_of_params])
        return self

    # -- совместимость со sqlite3.Cursor ----------------------------------
    @property
    def rowcount(self):
        return self._cur.rowcount

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def fetchmany(self, size=None):
        return self._cur.fetchmany(size) if size else self._cur.fetchmany()

    def close(self):
        self._cur.close()

    def __iter__(self):
        return iter(self._cur)




class Connection:
    """Лёгкая обёртка поверх соединения psycopg (из пула).

    Поведение подогнано под прежний sqlite3-код:
      * autocommit=True — каждое execute сразу фиксируется;
      * commit()/rollback() — no-op (безопасно для старого кода);
      * context manager НЕ закрывает соединение, а возвращает его в пул.
    """

    def __init__(self, raw, pool=None):
        self._raw = raw
        self._pool = pool
        self._cur = None          # ленивый общий курсор соединения

    def cursor(self):
        # Новый psycopg-курсор на каждый вызов: старый код местами пишет
        # store.connect().execute(...) без close() — переиспользование одного
        # ленивого курсора приводило бы к утечке курсоров внутри соединения.
        return Cursor(self._raw.cursor(row_factory=compat_dict_row))

    def execute(self, sql, params=None):
        # Возвращаем обёртку Cursor: внутри неё уже выполняется конвертация
        # плейсхолдеров '?' -> '%s' (см. b1416d9 — без неё бэкенд падал на
        # старте и nginx отдавал 502).
        return self.cursor().execute(sql, params)

    def executescript(self, script: str):
        """Выполнить несколько операторов DDL/DML одним заходом.

        psycopg3 (в отличие от sqlite3) не умеет выполнять скрипт с
        несколькими операторами за один execute — разбиваем по ';' и
        выполняем каждый оператор отдельно в одном транзакционном блоке.
        """
        with self._raw.transaction():
            for stmt in split_statements(script):
                self._raw.execute(stmt)
        return self.cursor()

    def commit(self):
        pass  # autocommit

    def rollback(self):
        pass

    def close(self):
        try:
            _LEAKED.remove(self)      # перестать быть "сиротой" для TTL-сборщика
        except ValueError:
            pass
        raw, self._raw = self._raw, None
        cur, self._cur = self._cur, None
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        if raw is not None and self._pool is not None:
            self._pool.putconn(raw)
        elif raw is not None:
            raw.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False


_POOL: ConnectionPool | None = None
# Все выданные наружу обёртки (connect() без with/close) — сюда, для возврата
# в пул по TTL. Иначе legacy-код main.py (store.connect() как аргумент функции)
# удерживал бы соединения навсегда и пул исчерпывался за десятки запросов.
_LEAKED: list["Connection"] = []


def _reclaim_leaked(max_keep: int = 256) -> None:
    """Вернуть в пул соединения-сироты, живущие дольше PG_LEAK_TTL секунд."""
    import time as _t
    ttl = float(os.environ.get("PG_LEAK_TTL", "30"))
    now = _t.time()
    keep = []
    for c in _LEAKED:
        if now - getattr(c, "_born", 0) >= ttl:
            try:
                c.close()
            except Exception:
                pass
        else:
            keep.append(c)
    del _LEAKED[:]
    _LEAKED.extend(keep[-max_keep:])   # защита от бесконечного роста списка


def get_pool() -> ConnectionPool:
    """Ленивый пул без ожидания первого соединения (wait_on_close=False,
    timeout=None): если PostgreSQL недоступен, getconn() сразу бросает
    OperationalError вместо зависания на 30 секунд — иначе health-check
    платформы успевает убить процесс и весь сервис висит в 502."""
    global _POOL
    if _POOL is None:
        _POOL = ConnectionPool(
            conninfo=_database_url(),
            min_size=0,
            max_size=int(os.environ.get("POSTGRES_POOL_MAX", "10")),
            kwargs={"autocommit": True, "prepare_threshold": 0,
                    "connect_timeout": int(os.environ.get("PG_CONNECT_TIMEOUT", "5"))},
            open=True,
            timeout=10,
            max_idle=60,
            check=ConnectionPool.check_connection,
        )
    return _POOL


def check_connection() -> tuple[bool, str]:
    """Диагностика подключения для /health: (ok, сообщение)."""
    try:
        conn = connect()
        try:
            conn.execute("SELECT 1").fetchone()
        finally:
            conn.close()
        return True, "ok"
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:200]}"


def connect():
    """Вернуть PG-обёртку из пула (аналог sqlite3.connect для всего кода).

    Вызывающий код обязан закрыть соединение (with / .close()). Там, где это
    невозможно (старые места вроде crm.register_comm(store.connect(), ...)),
    соединение вернётся в пул автоматически по TTL (_reclaim_leaked).
    """
    _reclaim_leaked()
    conn = Connection(get_pool().getconn(), pool=get_pool())
    import time as _t
    conn._born = _t.time()
    _LEAKED.append(conn)
    return conn


def connection_factory(path: str):
    """Фабрика для sqlite3.dump(..., filename='pg', connection_factory=...):
    игнорирует имя файла, возвращает реальное PG-соединение."""
    return connect()

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


class Cursor:
    """Обёртка psycopg-cursora: '?'-плейсхолдеры + строки-словари."""

    def __init__(self, cur):
        self._cur = cur

    def execute(self, sql, params=None):
        self._cur.execute(qmark_to_format(sql), params or ())
        c = self._cur
        parent = getattr(self, "_parent", None)
        if parent is not None:
            parent._after(c)
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

    def cursor(self):
        cur = self._raw.cursor(row_factory=dict_row)
        w = Cursor(cur)
        w._parent = self
        return w

    def _after(self, executed_cur):
        # psycopg с autocommit=True сам закрывает предыдущий курсор при
        # новом запросе на соединении; это нормально — держим только текущий.
        self._last = executed_cur

    def execute(self, sql, params=None):
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
        raw, self._raw = self._raw, None
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


def get_pool() -> ConnectionPool:
    global _POOL
    if _POOL is None:
        _POOL = ConnectionPool(
            conninfo=_database_url(),
            min_size=1,
            max_size=int(os.environ.get("POSTGRES_POOL_MAX", "10")),
            kwargs={"autocommit": True, "prepare_threshold": 0},
            open=True,
            check=ConnectionPool.check_connection,
        )
    return _POOL


def connect():
    """Вернуть PG-обёртку из пула (аналог sqlite3.connect для всего кода)."""
    return Connection(get_pool().getconn(), pool=get_pool())


def connection_factory(path: str):
    """Фабрика для sqlite3.dump(..., filename='pg', connection_factory=...):
    игнорирует имя файла, возвращает реальное PG-соединение."""
    return connect()

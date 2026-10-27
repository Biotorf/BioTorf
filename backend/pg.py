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
    """Обёртка psycopg-курсора: '?'-плейсхолдеры + строки-словари.

    Хранит ссылку на Connection-обёртку (_owner) и выполняет SQL через её
    _run(): при «сломанном» соединении (сервер перезапустился, сеть моргнула)
    обёртка сама подменяет raw-соединение на свежее из пула и повторяет
    попытку — запрос не падает с 500/502.
    """

    def __init__(self, cur, owner=None):
        self._cur = cur
        self._owner = owner
        self._auto_release = None   # callable: вернуть соединение в пул после fetch

    def _rebind(self):
        """Вернуть курсор на свежее raw-соединение (после реконнекта владельца)."""
        if getattr(self._owner, "_transient", False):
            return   # временный курсор: соединение живёт до конца этого запроса
        try:
            if self._owner is not None and self._cur is not None \
                    and self._cur.connection is not self._owner._raw:
                self._cur.close()
        except Exception:
            pass
        try:
            self._cur = self._owner._live_raw().cursor(row_factory=compat_dict_row)
        except Exception:
            pass

    def execute(self, sql, params=None):
        psql = qmark_to_format(sql)
        args = tuple(params) if params else ()
        if self._owner is not None:
            transient = getattr(self._owner, "_transient", False)
            if transient:
                # одноразовый курсор: если владелец — авто-прокси (_AutoConn),
                # соединение вернётся в пул сразу после вычитки результата.
                # Долгоживущий курсор на авто-соединении оставлял бы его
                # занятым до TTL-сборщика и при опросе фронта каждые
                # несколько секунд исчерпывал весь пул ("waiting for a
                # connection ... timed out" -> 502).
                self._cur = self._owner._run_transient(psql, args)
            else:
                self._cur = self._owner._run(psql, args, self._cur)
        else:
            self._cur.execute(psql, args)
        return self

    def executemany(self, sql, seq_of_params):
        psql = qmark_to_format(sql)
        args = [tuple(p) for p in seq_of_params]
        if self._owner is not None:
            self._cur = self._owner._run_many(psql, args, self._cur)
        else:
            self._cur.executemany(psql, args)
        return self

    # -- совместимость со sqlite3.Cursor ----------------------------------
    @property
    def rowcount(self):
        return self._cur.rowcount

    def fetchone(self):
        try:
            return self._cur.fetchone()
        except (psycopg.OperationalError, psycopg.InterfaceError) as e:
            if self._owner is not None and self._owner._is_broken(e) \
                    and self._owner._replace_broken():
                self._rebind()
                return self._cur.fetchone()
            raise
        finally:
            self._release()

    def fetchall(self):
        try:
            return self._cur.fetchall()
        except (psycopg.OperationalError, psycopg.InterfaceError) as e:
            if self._owner is not None and self._owner._is_broken(e) \
                    and self._owner._replace_broken():
                self._rebind()
                return self._cur.fetchall()
            raise
        finally:
            self._release()

    def fetchmany(self, size=None):
        try:
            return self._cur.fetchmany(size) if size else self._cur.fetchmany()
        finally:
            self._release()

    def _release(self):
        """Одноразово вернуть авто-соединение _AutoConn в пул после вычитки."""
        rel, self._auto_release = self._auto_release, None
        if rel is not None:
            try:
                rel()
            except Exception:
                pass

    def close(self):
        self._release()
        self._cur.close()

    def __iter__(self):
        try:
            yield from self._cur
        finally:
            self._release()





class _ReleaseCursor:
    """Прокси psycopg-курсора: после fetch*/итерации автоматически закрывает
    курсор и возвращает его соединение в пул."""

    __slots__ = ("_cur", "_release")

    def __init__(self, cur, release):
        self._cur = cur
        self._release = release

    @property
    def rowcount(self):
        return self._cur.rowcount

    def fetchone(self):
        r = self._cur.fetchone()
        self._done()
        return r

    def fetchall(self):
        r = self._cur.fetchall()
        self._done()
        return r

    def fetchmany(self, size=None):
        r = self._cur.fetchmany(size) if size else self._cur.fetchmany()
        self._done()
        return r

    def _done(self):
        rel, self._release = self._release, None
        if rel:
            rel()

    def close(self):
        self._done()

    def __iter__(self):
        rows = self._cur.fetchall()
        self._done()
        return iter(rows)


class Connection:
    """Лёгкая обёртка поверх соединения psycopg (из пула).

    Поведение подогнано под прежний sqlite3-код:
      * autocommit=True — каждое execute сразу фиксируется;
      * commit()/rollback() — no-op (безопасно для старого кода);
      * context manager НЕ закрывает соединение, а возвращает его в пул.
    """

    _transient = False   # см. Cursor.execute: у Connection SQL идёт через _run

    def __init__(self, raw, pool=None, conninfo=""):
        self._raw = raw
        self._pool = pool
        self._conninfo = conninfo or getattr(raw, "dsn", "") or ""
        self._cur = None          # ленивый общий курсор соединения

    def _replace_broken(self):
        """Подменить «сломанное» raw-соединение на свежее из пула.

        Работает и для прямых (непуловых) соединений: там вместо возврата в
        пул просто открываем новое соединение по тем же параметрам conninfo.
        """
        if self._raw is None:
            return False
        if self._pool is not None:
            try:
                self._pool.putconn(self._raw, bad=True)  # закроет битвое, создаст новое
            except Exception:
                try:
                    self._raw.close()
                except Exception:
                    pass
            try:
                self._raw = self._pool.getconn(timeout=10)
                return True
            except Exception:
                self._raw = None
                return False
        # непущевое соединение: переподключаемся напрямую
        try:
            self._raw.close()
        except Exception:
            pass
        try:
            import psycopg as _ps
            new = _ps.connect(conninfo=self._conninfo, autocommit=True,
                              prepare_threshold=0, connect_timeout=5)
            self._raw = new
            return True
        except Exception:
            self._raw = None
            return False

    @staticmethod
    def _is_broken(e: Exception) -> bool:
        if not isinstance(e, (psycopg.OperationalError, psycopg.InterfaceError)):
            return False
        msg = str(e).lower()
        # таймаут ожидания свободного соединения из пула — это НЕ обрыв,
        # а исчерпание пула: переподключение тут не поможет
        if "waiting for a connection" in msg or "timed out" in msg and "pool" in msg:
            return False
        return True

    def _run(self, psql, args, cur):
        """Выполнить SQL; при обрыве соединения — один раз переподключиться."""
        for attempt in (0, 1):
            try:
                if cur is None or getattr(cur, "closed", True):
                    cur = self._live_raw().cursor(row_factory=compat_dict_row)
                cur.execute(psql, args)
                return cur
            except (psycopg.OperationalError, psycopg.InterfaceError) as e:
                try:
                    cur.close()
                except Exception:
                    cur = None
                if attempt == 0 and self._is_broken(e) and self._replace_broken():
                    cur = None
                    continue
                raise
        raise RuntimeError("unreachable")

    def _run_many(self, psql, seq, cur):
        for attempt in (0, 1):
            try:
                if cur is None or getattr(cur, "closed", True):
                    cur = self._live_raw().cursor(row_factory=compat_dict_row)
                cur.executemany(psql, seq)
                return cur
            except (psycopg.OperationalError, psycopg.InterfaceError) as e:
                try:
                    cur.close()
                except Exception:
                    cur = None
                if attempt == 0 and self._is_broken(e) and self._replace_broken():
                    cur = None
                    continue
                raise
        raise RuntimeError("unreachable")

    def _run_transient(self, psql, args):
        """Выполнить SQL на временном курсоре владельца (для _AutoConn)."""
        run = getattr(self._owner, "_run_transient", None)
        if run is not None:
            return run(psql, args)
        return self._owner._run(psql, args, self._cur)

    def _live_raw(self):
        """Вернуть рабочее raw-соединение; при обрыве — переподключиться."""
        if self._raw is None:
            if not self._replace_broken():
                raise psycopg.OperationalError("no usable PostgreSQL connection")
        elif self._raw.closed:
            if not self._replace_broken():
                raise psycopg.OperationalError("the connection is closed")
        return self._raw

    def cursor(self):
        # Новый psycopg-курсор на каждый вызов: старый код местами пишет
        # store.connect().execute(...) без close() — переиспользование одного
        # ленивого курсора приводило бы к утечке курсоров внутри соединения.
        return Cursor(self._live_raw().cursor(row_factory=compat_dict_row), owner=self)

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
        for attempt in (0, 1):
            try:
                raw = self._live_raw()
                with raw.transaction():
                    for stmt in split_statements(script):
                        raw.execute(stmt)
                break
            except (psycopg.OperationalError, psycopg.InterfaceError) as e:
                if attempt == 0 and self._is_broken(e) and self._replace_broken():
                    continue
                raise
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


class _AutoConn:
    """Прокси к пуловому соединению с автовозвратом в пул.

    Позволяет писать `crm.get_state(connect())` без close(): прокси берёт
    соединение из пула на время запроса и возвращает его сразу после — так
    пул не исчерпается даже при тысячах вызовов «утекающего» legacy-кода.
    Явные `with connect()` / `.close()` тоже работают (закрепляют соединение
    за собой до явного закрытия).
    """

    _transient = True    # см. Cursor.execute: каждый запрос — временное соединение

    def __init__(self):
        self._c: Connection | None = None   # закреплённое (with/close) соединение

    def _get(self) -> Connection:
        if self._c is not None:
            return self._c
        _reclaim_leaked()
        return Connection(get_pool().getconn(), pool=get_pool(), conninfo=_database_url())

    def _ret(self, c: Connection) -> None:
        if c is not self._c:                 # временное соединение прокси
            try:
                c.close()
            except Exception:
                pass

    def execute(self, sql, params=None):
        c = self._get()
        try:
            cur = c.execute(sql, params)
        except Exception:
            self._ret(c)
            raise
        if c is not self._c:                 # временное — вернём в пул после fetch
            cur._auto_release = lambda: self._ret(c)
        return cur

    def _run_transient(self, psql, args):
        """psycopg-курсор на временном пуловом соединении; соединение будет
        возвращено в пул сразу после выборки результатов этого курсора."""
        if self._c is not None:              # закреплённое with-соединение
            return self._c._live_raw().cursor(row_factory=compat_dict_row)
        raw = get_pool().getconn()
        try:
            raw.autocommit = True
            cur = raw.cursor(row_factory=compat_dict_row)
            cur.execute(psql, args)
        except Exception:
            try:
                raw.close()
            except Exception:
                pass
            raise
        def _ret():
            try:
                cur.close()
            except Exception:
                pass
            try:
                get_pool().putconn(raw)
            except Exception:
                try:
                    raw.close()
                except Exception:
                    pass
        return _ReleaseCursor(cur, _ret)

    def executescript(self, script):
        c = self._get()
        try:
            return c.executescript(script)
        finally:
            self._ret(c)

    def cursor(self):
        c = self._get()
        cur = c.cursor()
        if c is not self._c:
            cur._auto_release = lambda: self._ret(c)
        return cur

    def commit(self):
        c = self._get()
        try:
            c.commit()
        finally:
            self._ret(c)

    def rollback(self):
        c = self._get()
        try:
            c.rollback()
        finally:
            self._ret(c)

    # -- явное владение (with / close) -----------------------------------
    def close(self):
        if self._c is not None:
            self._c.close()
            self._c = None

    def __enter__(self):
        _reclaim_leaked()
        self._c = Connection(get_pool().getconn(), pool=get_pool(), conninfo=_database_url())
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False


def connect():
    """Вернуть PG-соединение (аналог sqlite3.connect для всего кода).

    Возвращает _AutoConn: соединения из пулa берутся/возвращаются прозрачно,
    поэтому места вида `crm.register_comm(store.connect(), ...)` (без close())
    больше не удерживают пул. `with store.connect() as conn:` работает как
    раньше.
    """
    return _AutoConn()


def connection_factory(path: str):
    """Фабрика для sqlite3.dump(..., filename='pg', connection_factory=...):
    игнорирует имя файла, возвращает реальное PG-соединение."""
    return connect()

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

import logging
import os
import re
import time

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, PoolTimeout

# Ошибки ожидания пула: при недоступном PostgreSQL getconn() бросает
# PoolTimeout (не подкласс psycopg.Error!) — ловим его везде, где берём
# соединение, чтобы отдавать аккуратный 503 вместо падения с 500.
_POOL_ERRORS = (psycopg.OperationalError, PoolTimeout)

log = logging.getLogger("biotorf.pg")


def _table_from_sql(sql: str) -> str:
    """Имя таблицы из SQL — для коротких, читаемых логов ошибок."""
    m = re.search(
        r"\b(?:FROM|INTO|UPDATE|TABLE(?:\s+IF\s+(?:NOT\s+)?EXISTS)?|JOIN)\s+[\"`]?([\w.]+)",
        sql or "", re.IGNORECASE)
    return m.group(1) if m else "?"


def is_missing_relation(e: BaseException) -> bool:
    """True, если psycopg-ошибка — «таблица/отношение не существует» (42P01)."""
    return getattr(e, "sqlstate", None) == "42P01"


def _ensure_comms_table(raw) -> None:
    """Самовосстановление: создать comms + индексы, если их нет (42P01)."""
    raw.execute("""
CREATE TABLE IF NOT EXISTS comms (
    seq          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id           TEXT NOT NULL UNIQUE,
    kind         TEXT NOT NULL,
    dir          TEXT NOT NULL DEFAULT 'in' CHECK (dir IN ('in','out')),
    farm_id      TEXT,
    contact      TEXT,
    phone        TEXT,
    handle       TEXT,
    ts           TEXT NOT NULL,
    duration     INTEGER NOT NULL DEFAULT 0,
    status       TEXT,
    text         TEXT,
    note         TEXT,
    read         INTEGER NOT NULL DEFAULT 0,
    source       TEXT NOT NULL DEFAULT 'manual',
    external_id  TEXT,
    payload      TEXT,
    peer_key     TEXT
)""")
    for stmt in (
        "CREATE INDEX IF NOT EXISTS idx_comms_ts     ON comms (ts DESC)",
        "CREATE INDEX IF NOT EXISTS idx_comms_farm   ON comms (farm_id)",
        "CREATE INDEX IF NOT EXISTS idx_comms_unread ON comms (read)",
        "CREATE INDEX IF NOT EXISTS idx_comms_seq    ON comms (seq)",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_comms_ext ON comms (source, external_id)",
    ):
        raw.execute(stmt)


def _ensure_chat_drafts_table(raw) -> None:
    raw.execute("""
CREATE TABLE IF NOT EXISTS chat_drafts (
    peer_key TEXT PRIMARY KEY,
    draft    TEXT NOT NULL DEFAULT '',
    updated  TEXT NOT NULL
)""")


# имя отношения из PG-сообщения об ошибке (relation "chat_drafts" does not exist)
_RELATION_RE = re.compile(r'relation "([\w.]+)" does not exist')

# самовосстановление после падения /health-подобных циклов: не чаще одного
# восстановления на таблицу в PG_HEAL_COOLDOWN секунд (защита от шторма DDL)
_HEALED: dict[str, float] = {}


def _heal_missing_relation(raw, err_text: str) -> bool:
    """Создать отсутствующую таблицу и вернуть True, если это удалось.

    Лечим только известные нам таблицы схемы; cooldown защищает от частых
    повторов при конкурентном доступе нескольких потоков."""
    m = _RELATION_RE.search(err_text or "")
    if not m:
        return False
    name = m.group(1)
    now = time.time()
    if now - _HEALED.get(name, 0.0) < float(os.environ.get("PG_HEAL_COOLDOWN", "30")):
        return False
    try:
        if name == "comms":
            _ensure_comms_table(raw)
        elif name == "chat_drafts":
            _ensure_chat_drafts_table(raw)
        else:
            return False   # неизвестную таблицу сами не создаём
        _HEALED[name] = now
        log.warning("[db] таблица %s отсутствовала — создана автоматически "
                    "(схема была неполной; проверьте миграцию schema.sql)", name)
        return True
    except Exception as e2:
        _HEALED[name] = now   # не крутить DDL при каждой ошибке
        log.error("[db] не удалось восстановить таблицу %s: %s", name, e2)
        return False


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
        self._sql = ""              # последний выполненный SQL (для возврата
                                    # авто-соединения при INSERT/UPDATE без fetch)
        self._closed = False        # явный флаг close(): сырой psycopg-курсор
                                    # после .close() НЕ выбрасывает исключение
                                    # при повторном закрытии, поэтому `finally:
                                    # self.close()` в executescript зацикливался
                                    # и никогда не вызывал _unpin_release
                                    # (инцидент PoolTimeout 2026-10-28 00:40)

    @staticmethod
    def _close_raw(cur_obj):
        """Закрыть настоящий psycopg-курсор (или цепочку прокси _ReleaseCursor)."""
        seen = set()
        while cur_obj is not None and id(cur_obj) not in seen:
            seen.add(id(cur_obj))
            try:
                cur_obj.close()
                return
            except Exception:
                nxt = getattr(cur_obj, "_cur", None)
                if nxt is cur_obj or nxt is None:
                    return
                cur_obj = nxt

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

    @staticmethod
    def _returns_rows(sql: str) -> bool:
        """True, если оператор отдаёт строки (SELECT/WITH/... RETURNING/FETCH/SHOW/EXPLAIN)."""
        m = re.search(r"\bRETURNING\b", sql or "", re.IGNORECASE)
        if m and not re.match(r"^\s*(--|/\*)*\s*INSERT\b", sql or "", re.IGNORECASE):
            return True          # комментарий внутри 'INSERT ...' не в счёт
        head = re.sub(r"^\s*(?:--[^\n]*\n|/\*.*?\*/|\s)+", "", sql or "",
                      flags=re.DOTALL).upper()
        return head.startswith(("SELECT", "WITH", "VALUES", "TABLE", "FETCH",
                                 "SHOW", "EXPLAIN"))

    def _maybe_release_nonselect(self):
        """INSERT/UPDATE/DELETE без RETURNING ничего не отдают на fetch.

        Если соединение закреплено за прокси (_AutoConn._c) и это последний
        открытый курсор этого соединения — снимаем закрепку и возвращаем
        соединение в пул немедленно (putconn). Иначе «пустой» write держал бы
        соединение до явного close()/TTL-сборщика, а при опросе фронта каждые
        несколько секунд это забивало весь пул (PoolTimeout -> 503, инцидент
        2026-10-28 00:40).

        Курсор при этом НЕ закрываем: вызывающий код может ещё обратиться к
        rowcount/lastrowid; соединение освободится после закрытия курсора
        (см. Connection.close -> _close_open_cursors)."""
        if self._returns_rows(self._sql):
            return
        owner = self._owner                       # Cursor -> Connection
        proxy = getattr(owner, "_owner", None)    # Connection -> _AutoConn
        if proxy is None or getattr(proxy, "_c", None) is not owner:
            return                                # не наше закреплённое соединение
        if getattr(proxy, "_in_with", False):
            return                                # with-блок:release в __exit__
        try:
            rc = self._cur.rowcount               # -1: строки есть (RETURNING) — ждём fetch
        except Exception:
            return
        if rc == -1:
            return
        if any(c is not None and c is not self._cur and not c.closed
               for c in getattr(owner, "_open_cursors", ())):
            return                                # конкурентный курсор ещё жив
        proxy._unpin_release()

    @property
    def closed(self):
        # ВАЖНО: сырой psycopg-курсор после .close() НЕ бросает исключение при
        # повторном закрытии — полагаться только на self._cur.closed нельзя,
        # иначе `finally: self.close()` (executescript) не срабатывал никогда.
        if self._closed:
            return True
        try:
            return bool(self._cur.closed)
        except Exception:
            return True

    def execute(self, sql, params=None):
        psql = qmark_to_format(sql)
        args = tuple(params) if params else ()
        self._sql = sql
        try:
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
        except psycopg.Error as e:
            # Единственная точка, где все SQL-ошибки бэкенда встречаются с
            # логом: раньше ошибка уходила в FastAPI как "Internal Server
            # Error" без стека, и по логу нельзя было понять, какой запрос
            # упал и на какой таблице (например, отсутствующей chat_drafts).
            log.error(
                "[db] SQL failed: %s | table=%s | params=%d | %.300s",
                type(e).__name__, _table_from_sql(sql), len(args), str(e).replace("\n", " "))
            raise
        self._maybe_release_nonselect()
        return self

    def executemany(self, sql, seq_of_params):
        psql = qmark_to_format(sql)
        args = [tuple(p) for p in seq_of_params]
        self._sql = sql
        try:
            if self._owner is not None:
                self._cur = self._owner._run_many(psql, args, self._cur)
            else:
                self._cur.executemany(psql, args)
        except psycopg.Error as e:
            log.error(
                "[db] SQL(executemany) failed: %s | table=%s | rows=%d | %.300s",
                type(e).__name__, _table_from_sql(sql), len(args), str(e).replace("\n", " "))
            raise
        self._maybe_release_nonselect()
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
        if not self._closed:
            self._closed = True
            try:
                self._cur.close()
            except Exception:
                pass

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

    def __init__(self, raw, pool=None, conninfo="", registered=True):
        self._raw = raw
        self._pool = pool
        self._conninfo = conninfo or getattr(raw, "dsn", "") or ""
        self._cur = None          # ленивый общий курсор соединения
        self._born = time.time()  # для TTL-сборщика _reclaim_leaked
        self._registered = False
        self._released = False    # сырое соединение уже возвращено в пул
                                  # (putconn) — повторный возврат запрещён
        # Все открытые psycopg-курсоры этого соединения. Нужны, чтобы:
        #   1) close() гарантированно доcloseивал ВСЕ курсоры перед putconn
        #      (psycopg иначе считает соединение занятым и оно навсегда
        #      выпадает из available -> PoolTimeout, инцидент 2026-10-28);
        #   2) _maybe_release_nonselect не отпускал соединение, пока другой
        #      курсор ещё жив.
        self._open_cursors: list = []
        self._owner = None        # _AutoConn, породивший это соединение (см. _pin)
        if pool is not None and registered:
            # Регистрация в списке «сирот»: обёртки, созданные connect() без
            # with/close (legacy-код crm.put_state(store.connect(), ...) и т.п.),
            # иначе повиснут навсегда и исчерпают пул (PoolTimeout -> 500).
            # close()/putconn снимают регистрацию (см. close()).
            # registered=False — для курсоров с авто-возвратом (_AutoConn):
            # они отпускаются сами в fetch/finally, а по TTL сборщик вернул бы
            # в пул соединение, которое ЭТО ЖЕ курсор ещё читает (двойной
            # putconn -> PoolTimeout при живом PostgreSQL).
            try:
                _LEAKED.append(self)
                self._registered = True
            except Exception:
                pass

    def _replace_broken(self):
        """Подменить «сломанное» raw-соединение на свежее из пула.

        Работает и для прямых (непуловых) соединений: там вместо возврата в
        пул просто открываем новое соединение по тем же параметрам conninfo.

        Перед заменой закрываем ВСЕ курсоры старого соединения: иначе они
        навсегда повиснут внутри мёртвого raw-соединения (утечка памяти и
        открытых сокетов на стороне сервера при частых обрывах).
        """
        try:
            self._close_open_cursors()
        except Exception:
            pass
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
        """Выполнить SQL; при обрыве соединения — один раз переподключиться.

        Отдельно лечим «таблица не существует» (42P01): если инициализация
        схемы не успела или прошла наполовину (например, упала на первой
        же ошибке), отсутствующая таблица comms/chat_drafts создаётся на
        месте и запрос повторяется — вместо 500-ки на каждом автосохранении
        черновика с фронта.

        ВАЖНО (инцидент PoolTimeout 2026-10-28 00:40): перед созданием нового
        курсора старый ОБЯЗАТЕЛЬНО закрывается. psycopg при putconn() ждёт
        закрытия всех курсоров соединения; незакрытый курсор после REPLACE
        (SELECT ... RETURNING / INSERT ... ON CONFLICT DO UPDATE — их rowcount
        равен -1, см. Cursor._maybe_release_nonselect) оставлял соединение
        «занятым навсегда», и пул из 10 соединений забивался за минуту при
        обычном опросе фронта -> PoolTimeout -> 503 на всех эндпоинтах."""
        for attempt in (0, 1, 2):
            try:
                if cur is None or getattr(cur, "closed", True):
                    if cur is not None:      # мёртвый курсор — доcloseить
                        Cursor._close_raw(cur)
                    cur = self._new_cursor()
                cur.execute(psql, args)
                return cur
            except psycopg.Error as e:
                try:
                    cur.close()
                except Exception:
                    cur = None
                if attempt == 0 and is_missing_relation(e) \
                        and _heal_missing_relation(self._live_raw(), str(e)):
                    cur = None
                    continue
                if isinstance(e, (psycopg.OperationalError, psycopg.InterfaceError)) \
                        and attempt == 0 and self._is_broken(e) and self._replace_broken():
                    cur = None
                    continue
                raise
        raise RuntimeError("unreachable")

    def _new_cursor(self):
        """Новый psycopg-курсор; регистрируется в _open_cursors, чтобы close()
        гарантированно закрыл ВСЕ курсоры перед putconn (иначе соединение
        навсегда останется «занятым» — PoolTimeout, инцидент 2026-10-28)."""
        cur = self._live_raw().cursor(row_factory=compat_dict_row)
        lst = self._open_cursors
        # чистим уже закрытые, чтобы список не рос бесконечно
        if len(lst) > 4:
            try:
                self._open_cursors = lst = [c for c in lst if not c.closed]
            except Exception:
                pass
        lst.append(cur)
        return cur

    def _close_open_cursors(self):
        for c in self._open_cursors:
            try:
                c.close()
            except Exception:
                pass
        self._open_cursors = []

    def _run_many(self, psql, seq, cur):
        for attempt in (0, 1, 2):
            try:
                if cur is None or getattr(cur, "closed", True):
                    if cur is not None:      # см. _run: доcloseить мёртвый курсор
                        Cursor._close_raw(cur)
                    cur = self._new_cursor()
                cur.executemany(psql, seq)
                return cur
            except psycopg.Error as e:
                try:
                    cur.close()
                except Exception:
                    cur = None
                if attempt == 0 and is_missing_relation(e) \
                        and _heal_missing_relation(self._live_raw(), str(e)):
                    cur = None
                    continue
                if isinstance(e, (psycopg.OperationalError, psycopg.InterfaceError)) \
                        and attempt == 0 and self._is_broken(e) and self._replace_broken():
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
        return Cursor(self._new_cursor(), owner=self)

    def execute(self, sql, params=None):
        # Возвращаем обёртку Cursor: внутри неё уже выполняется конвертация
        # плейсхолдеров '?' -> '%s' (см. b1416d9 — без неё бэкенд падал на
        # старте и nginx отдавал 502).
        return self.cursor().execute(sql, params)

    def executescript(self, script: str):
        """Выполнить несколько операторов DDL/DML одним заходом.

        psycopg3 (в отличие от sqlite3) не умеет выполнять скрипт с
        несколькими операторами за один execute — разбиваем по ';' и
        выполняем каждый оператор ОТДЕЛЬНО (без общей транзакции). Раньше
        всё шло в одном raw.transaction(): один битый оператор откатывал
        ВЕСЬ скрипт, и база оставалась с неполной схемой (например, comms
        создана, chat_drafts — нет → PUT /api/chat/*/draft падал в 500 на
        каждом автосохранении черновика с фронта). CREATE ... IF NOT EXISTS
        идемпотентны, поэтому частичное применение безопасно: повторный
        пропуск доделывает схему."""
        raw = self._live_raw()
        for stmt in split_statements(script):
            try:
                raw.execute(stmt)
            except psycopg.Error as e:
                if isinstance(e, (psycopg.OperationalError, psycopg.InterfaceError)) \
                        and self._is_broken(e) and self._replace_broken():
                    raw = self._live_raw()
                    try:
                        raw.execute(stmt)   # одна попытка на свежем соединении
                        continue
                    except psycopg.Error as e2:
                        log.warning("[db] DDL skipped after reconnect: %.200s", str(e2))
                        continue
                # отдельный оператор не прошёл (конкурентный CREATE, права и
                # т.п.) — остальные применяем; неполноту схемы увидит и
                # залечит проверка _ensure_schema/_missing_pg_tables
                log.warning("[db] DDL skipped (%s): stmt=%.120s err=%.200s",
                            type(e).__name__, stmt.replace("\n", " "), str(e))
        # Возвращаем ЗАКРЫТЫЙ курсор-обёртку: вызывающий код db.py пишет
        # `finally: cur.close()` и ожидает идемпотентного закрытия. Открытый
        # курсор здесь оставил бы соединение «занятым» в пуле (см. close()).
        done = Cursor(None, owner=self)
        done._closed = True
        return done

    def commit(self):
        pass  # autocommit

    def rollback(self):
        pass

    def close(self):
        raw, self._raw = self._raw, None
        cur, self._cur = self._cur, None
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        # КРИТИЧНО (инцидент PoolTimeout 2026-10-28): до putconn закрыть ВСЕ
        # открытые курсоры соединения. psycopg не считает соединение свободным,
        # пока у него живы курсоры — такое соединение «навсегда» выпадает из
        # available и пул исчерпывается за минуту при опросе фронта.
        try:
            self._close_open_cursors()
        except Exception:
            pass
        if self._registered:
            try:
                _LEAKED.remove(self)  # перестать быть "сиротой" для TTL-сборщика
            except ValueError:
                pass
            self._registered = False
        if raw is not None and self._pool is not None and not self._released:
            self._released = True
            self._pool.putconn(raw)
        elif raw is not None and self._pool is None:
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
import threading as _threading
_LEAK_LOCK = _threading.Lock()


def _reclaim_leaked(max_keep: int = 256) -> None:
    """Вернуть в пул соединения-сироты, живущие дольше PG_LEAK_TTL секунд.

    Поток-безопасность: снимаем обёртки из списка ПОД замком и закрываем
    (putconn) уже вне его — close() может блокироваться на сетке с PostgreSQL.
    Повторный putconn исключён флагом _released в Connection.close().

    Адаптивный TTL: при высокой загрузке пула (>=80% занятых) сироты старше
    5 секунд回收ятся сразу — legacy-код держит соединения без close(), и при
    опросе фронта каждые несколько секунд обычный TTL=30 не успевал бы
    освобождать пул между пиками (инцидент PoolTimeout 2026-10-28)."""
    import time as _t
    ttl = float(os.environ.get("PG_LEAK_TTL", "30"))
    busy, mx = _pool_pressure()
    if mx and busy >= mx * 0.8:
        ttl = min(ttl, 5.0)
    now = _t.time()
    with _LEAK_LOCK:
        expired = []
        keep = []
        for c in _LEAKED:
            if now - getattr(c, "_born", 0) >= ttl:
                expired.append(c)
            else:
                keep.append(c)
        del _LEAKED[:]
        _LEAKED.extend(keep[-max_keep:])   # защита от бесконечного роста списка
    for c in expired:
        try:
            c.close()
        except Exception:
            pass


def _pool_pressure() -> tuple[int, int]:
    """(занятых в пуле, max_size) — для адаптивного TTL ниже."""
    try:
        st = get_pool().get_stats()
        busy = int(st.get("pool_size", 0)) - int(st.get("pool_available", 0))
        return busy, int(st.get("pool_max", 10)) or 10
    except Exception:
        return 0, 10


def get_pool() -> ConnectionPool:
    """Ленивый пул с быстрым отказом при недоступной базе.

    min_size=0 + timeout=3: пул не создаёт соединений в фоне и не ждёт их
    при старте процесса; getconn() при недоступном PostgreSQL бросает
    PoolTimeout за ~3 секунды вместо зависания на десятки секунд. Раньше
    блокирующий пул вешал startup-хук, health-check платформы не дожидался
    /health, убивал контейнер — и весь стек падал через 20–30 секунд после
    деплоя («работало и упало»)."""
    global _POOL
    if _POOL is None:
        _POOL = ConnectionPool(
            conninfo=_database_url(),
            min_size=0,
            max_size=int(os.environ.get("POSTGRES_POOL_MAX", "10")),
            kwargs={"autocommit": True, "prepare_threshold": 0,
                    "connect_timeout": int(os.environ.get("PG_CONNECT_TIMEOUT", "5"))},
            open=True,
            timeout=3,            # быстрый отказ вместо зависания на десятки секунд
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
        self._in_with = False               # внутри with-блока (release в __exit__)

    def _get(self) -> Connection:
        if self._c is not None:
            return self._c
        _reclaim_leaked()
        # ЕДИНСТВЕННЫЙ владелец пулового соединения — сама обёртка Connection
        # (зарегистрирована в _LEAKED; TTL-сборщик закрывает сироты, close()
        # снимает регистрацию). Прежняя схема «временная обёртка + _ret»
        # роняла пул: на каждом запросе создавалась новая обёртка с новым
        # курсором, старый курсор оставался открытым внутри raw-соединения,
        # putconn не возвращал его в available (psycopg ждёт закрытия курсоров),
        # и за минуту 8 потоков заполняли весь пул «висячими» соединениями
        # (PoolTimeout при живом PostgreSQL, инцидент 2026-10-28 00:40).
        c = Connection(get_pool().getconn(), pool=get_pool(), conninfo=_database_url())
        c._owner = self                     # для _maybe_release_nonselect
        return c

    def _pin(self, c: Connection) -> None:
        """Закрепить соединение за прокси до конца операции (см. execute())."""
        old = self._c
        if old is not None and old is not c:   # прежнее закреплённое освободить
            try:
                old.close()
            except Exception:
                pass
        self._c = c
        if c is not None:
            c._owner = self                    # для _maybe_release_nonselect

    def _unpin_release(self) -> None:
        """Снять закрепку и вернуть соединение в пул (см. _maybe_release_nonselect)."""
        c, self._c = self._c, None
        if c is not None:
            try:
                c.close()
            except Exception:
                pass

    def _ret(self, c: Connection) -> None:
        if c is not self._c:                 # чужое/уже откреплённое — не трогаем
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
        # Закрепляем соединение за прокси: все курсоры этого соединения
        # переиспользуются (см. Connection._run), а возврат в пул произойдёт
        # либо при явном close(), либо TTL-сборщиком (_LEAKED) — но никогда
        # посреди незавершённой операции вызывающего кода.
        self._pin(c)
        return cur

    def _run_transient(self, psql, args):
        """Выполнить SQL на текущем закреплённом соединении прокси.

        ВАЖНО: раньше здесь шёл прямой getconn() из пула с putconn в замыкании
        _ReleaseCursor — но этот путь вызывается из Cursor.execute при
        owner=_AutoConn, т.е. соединение УЖЕ взято в _get(), и повторный
        getconn() на каждый запрос удваивал нагрузку на пул (инцидент
        PoolTimeout 2026-10-28 00:40). Теперь запрос выполняется на том же
        соединении через Connection._run (переиспользование курсора, лечение
        42P01/обрывов); возврат в пул — по close()/TTL-сборщику.
        """
        if self._c is not None:
            return self._c._run(psql, args, None)
        # без закреплённого соединения (страховочный путь): одноразовое
        # временное соединение с гарантированным putconn после вычитки
        raw = get_pool().getconn()
        try:
            raw.autocommit = True
            cur = raw.cursor(row_factory=compat_dict_row)
            cur.execute(psql, args)
        except psycopg.Error:
            try:
                cur.close()
            except Exception:
                pass
            try:
                get_pool().putconn(raw, bad=True)
            except Exception:
                try:
                    raw.close()
                except Exception:
                    pass
            raise
        def _ret(cur=cur, raw=raw):
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

    def _release_after_ddl(self, c: Connection) -> None:
        """executescript не возвращает строк — после применения DDL снимаем
        закрепку и возвращаем соединение в пул немедленно (иначе каждый шаг
        инициализации схемы держал бы по соединению из 10 до TTL-сборщика;
        инцидент PoolTimeout 2026-10-28 00:40)."""
        if self._in_with:
            return                           # with-блок: release в __exit__
        if c is self._c:
            self._unpin_release()
        else:
            try:
                c.close()
            except Exception:
                pass

    def executescript(self, script):
        c = self._get()
        self._pin(c)                         # закрепляем ДО выполнения: при
                                             # падении mid-script соединение всё
                                             # равно будет закрыто в except
        try:
            res = c.executescript(script)
        except Exception:
            self._ret(c)                     # если ещё закреплено — открепить+close
            raise
        self._release_after_ddl(c)
        return res

    def cursor(self):
        c = self._get()
        cur = c.cursor()
        self._pin(c)
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
        # registered=False: обёртки, создаваемые в with-блоке, закрываются
        # гарантированно в __exit__ (даже при исключении). Если оставить их в
        # _LEAKED, то при медленном теле with (>TTL) сборщик вернул бы сырое
        # соединение в пул ДО выхода из блока — двойной putconn и повреждение
        # пула (PoolTimeout при живом PostgreSQL, см. инцидент 2026-10-28).
        self._c = Connection(get_pool().getconn(), pool=get_pool(),
                             conninfo=_database_url(), registered=False)
        self._c._owner = self
        self._in_with = True
        return self

    def __exit__(self, exc_type, exc, tb):
        self._in_with = False
        self.close()
        return False


def connect():
    """Вернуть PG-соединение (аналог sqlite3.connect для всего кода).

    Возвращает _AutoConn: соединения из пула берутся/возвращаются прозрачно,
    поэтому места вида `crm.register_comm(store.connect(), ...)` (без close())
    больше не удерживают пул. `with store.connect() as conn:` работает как
    раньше.

    Если PostgreSQL недоступен или пул исчерпан — вместо падения с 500
    (PoolTimeout) возвращается заглушка, в которой любая попытка взять
    соединение бросает psycopg.OperationalError: эндпоинты намеренно отдают
    понятную ошибку, а main.py переводит её в аккуратный 503.
    """
    try:
        pool = get_pool()
    except _POOL_ERRORS as e:
        log.warning("[db] пул недоступен (%s): %s", type(e).__name__, str(e)[:160])
        return _UnavailableConn(str(e))
    # Проверка реальной доступности: при выключенном PostgreSQL getconn()
    # бросает PoolTimeout через ~timeout секунд; без этой проверки он улетел
    # бы наружу из первого же execute() как необработанная 500-ка.
    try:
        raw = pool.getconn(timeout=2)
    except _POOL_ERRORS as e:
        return _UnavailableConn(f"{type(e).__name__}: {str(e)[:160]}")
    try:
        pool.putconn(raw)
    except Exception:
        pass
    return _AutoConn()


class _UnavailableConn:
    """Заглушка на время недоступности БД: execute/cursor бросают
    OperationalError (его ловят и middleware, и фоновые ретраи схемы)."""

    _transient = True

    def __init__(self, reason: str = ""):
        self._reason = reason or "no usable PostgreSQL connection"

    def _fail(self, *a):
        raise psycopg.OperationalError(self._reason)

    execute = executemany = executescript = cursor = commit = rollback = close = _fail

    def __enter__(self):
        self._fail()

    def __exit__(self, *a):
        return False


def connection_factory(path: str):
    """Фабрика для sqlite3.dump(..., filename='pg', connection_factory=...):
    игнорирует имя файла, возвращает реальное PG-соединение."""
    return connect()

"""CRM ядро BIOTORF Business OS: сквозной процесс и операционные реестры.

Хранилище — PostgreSQL (таблица crm_records; legacy-режим SQLite). Каждая запись
лежит в JSON-колонке data, коллекция — в поле _coll. Такой «документный» подход
позволяет фронтенду (stores/db.js) синхронизировать любые сущности без миграций
схемы при изменении полей.

Коллекции (см. руководство v0.9):
  farms, leads, deals, journeys, pilots, quotes, orders, invoices,
  shipments, tasks, contacts, clientNotes, applications, payments, media, social

API (подключается в main.py префиксом /api/crm):
  GET    /api/crm/state                 — весь снимок данных
  PUT    /api/crm/state                 — атомарное сохранение изменённых записей
  GET    /api/crm/{coll}                — список записей коллекции
  POST   /api/crm/{coll}                — создать запись
  PUT    /api/crm/{coll}/{rid}          — заменить запись
  DELETE /api/crm/{coll}/{rid}          — удалить запись
  GET    /api/crm/journeys/{jid}/process— собранный сквозной процесс:
         journey + lead + farm + deal + pilot + quote + order + invoice +
         shipment + tasks (всё, что связано с маршрутом)
"""

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

COLLECTIONS = (
    "farms", "leads", "deals", "journeys", "pilots", "quotes", "orders",
    "invoices", "shipments", "tasks", "contacts", "clientNotes",
    "applications", "payments", "media", "social", "knowledge", "skus",
    "warehouse", "production", "clientDocs",
)

OPTION_LISTS = frozenset({
    "regions", "crops", "sources", "owners", "statuses", "types", "unitPack",
    "locations", "transport", "drivers", "plates", "shifts", "operators",
    "platforms", "products", "priorities", "methods", "categories",
})
OPTION_COLLECTION = "crmOptions"


def get_options(conn) -> dict:
    options = {}
    for record in list_records(conn, OPTION_COLLECTION):
        options.setdefault(record["listKey"], []).append(record["value"])
    return options


def add_options(conn, options: dict) -> dict:
    rows = []
    for key, values in options.items():
        if key not in OPTION_LISTS or not isinstance(values, list):
            raise ValueError("Неизвестный справочник или неверный список значений")
        for raw in values:
            if not isinstance(raw, str) or not (value := raw.strip()) or len(value) > 500:
                raise ValueError("Значение справочника должно содержать от 1 до 500 символов")
            identity = hashlib.sha256(f"{key}:{value.casefold()}".encode()).hexdigest()
            data = json.dumps({"listKey": key, "value": value}, ensure_ascii=False)
            rows.append((identity, OPTION_COLLECTION, data, _now()))

    with write_transaction(conn) as tx:
        tx.executemany(
            "INSERT INTO crm_records (id, coll, data, updated) VALUES (?,?,?,?) "
            "ON CONFLICT(coll,id) DO NOTHING",
            rows,
        )
        return get_options(tx)


SCHEMA_CRM = """
CREATE TABLE IF NOT EXISTS crm_records (
    id       TEXT NOT NULL,
    coll     TEXT NOT NULL,
    data     TEXT NOT NULL,
    updated  TEXT NOT NULL,
    PRIMARY KEY (coll, id)
);
CREATE INDEX IF NOT EXISTS idx_crm_coll ON crm_records (coll);
"""


def init_tables(conn) -> None:
    """В postgres-режиме схема создаётся schema.sql — здесь только SQLite."""
    import db as _store
    if _store.IS_POSTGRES:
        return
    conn.executescript(SCHEMA_CRM)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_rec(row) -> dict:
    d = json.loads(row[1])
    d["id"] = row[0]
    d["_updatedAt"] = row[2]
    return d


# ── CRUD ────────────────────────────────────────────────────────────

def list_records(conn, coll: str) -> list[dict]:
    rows = conn.execute(
        "SELECT id, data, updated FROM crm_records WHERE coll=? ORDER BY updated DESC",
        (coll,),
    ).fetchall()
    return [_row_to_rec(r) for r in rows]


def get_record(conn, coll: str, rid: str) -> dict | None:
    row = conn.execute(
        "SELECT id, data, updated FROM crm_records WHERE coll=? AND id=?", (coll, rid)
    ).fetchone()
    return _row_to_rec(row) if row else None


@contextmanager
def write_transaction(conn):
    """Serialize read–modify–write operations while allowing concurrent readers."""
    if isinstance(conn, sqlite3.Connection):
        conn.execute("BEGIN IMMEDIATE")
        with conn:
            yield conn
    else:
        with conn.transaction() as tx:
            tx.execute("LOCK TABLE crm_records IN SHARE ROW EXCLUSIVE MODE")
            yield tx


_NO_REVISION = object()
_DELETED_PREFIX = "crmDeleted:"


class ConflictError(Exception):
    def __init__(self, coll: str, rid: str):
        super().__init__(f"{coll}/{rid}")
        self.coll, self.rid = coll, rid


def _row_id(value, coll: str) -> str:
    if value in (None, ""):
        return _gen_id(coll)
    if not isinstance(value, (str, int)) or isinstance(value, bool) or not str(value).strip():
        raise ValueError("ID записи должен быть непустой строкой")
    return str(value).strip()


def _record_data(rec: dict, rid: str) -> dict:
    return {**{k: v for k, v in rec.items() if k not in ("_updatedAt", "_expectedRev", "_delete")}, "id": rid}


def _write(tx, coll: str, rec: dict, rid: str) -> dict:
    stamp = _now()
    tx.execute(
        "INSERT INTO crm_records (id, coll, data, updated) VALUES (?,?,?,?) "
        "ON CONFLICT(coll,id) DO UPDATE SET data=excluded.data, updated=excluded.updated",
        (rid, coll, json.dumps(rec, ensure_ascii=False, allow_nan=False), stamp),
    )
    return {**rec, "_updatedAt": stamp}


def upsert(conn, coll: str, rec: dict, rid: str | None = None, *, merge=False, require_existing=False) -> dict | None:
    rid = _row_id(rid or rec.get("id"), coll)
    expected = rec.get("_expectedRev", _NO_REVISION)
    with write_transaction(conn) as tx:
        current = get_record(tx, coll, rid)
        if require_existing and current is None:
            if expected is not _NO_REVISION:
                raise ConflictError(coll, rid)
            return None
        if expected is not _NO_REVISION and expected != (current or {}).get("_updatedAt"):
            raise ConflictError(coll, rid)
        document = _record_data({**current, **rec} if merge and current else rec, rid)
        if current and document == _record_data(current, rid):
            return current
        return _write(tx, coll, document, rid)


def _remember_deletions(tx, coll: str, rid: str | None = None):
    where = "coll=?" + (" AND id=?" if rid is not None else "")
    args = (coll, rid) if rid is not None else (coll,)
    tx.execute(
        "INSERT INTO crm_records (id, coll, data, updated) "
        "SELECT id, ?, '{}', ? FROM crm_records WHERE " + where + " "
        "ON CONFLICT(coll,id) DO NOTHING",
        (_DELETED_PREFIX + coll, _now(), *args),
    )


def delete(conn, coll: str, rid: str, expected_revision=None) -> bool:
    with write_transaction(conn) as tx:
        current = get_record(tx, coll, rid)
        if current is None:
            return False
        if expected_revision is not None and expected_revision != current["_updatedAt"]:
            raise ConflictError(coll, rid)
        _remember_deletions(tx, coll, rid)
        tx.execute("DELETE FROM crm_records WHERE coll=? AND id=?", (coll, rid))
        return True


def _gen_id(coll: str) -> str:
    prefix = {
        "farms": "F", "leads": "L", "deals": "D", "journeys": "J", "pilots": "P",
        "quotes": "Q", "orders": "O", "invoices": "INV", "shipments": "SH",
        "tasks": "T", "contacts": "CT", "clientNotes": "N", "payments": "PAY",
        "applications": "AP", "clientDocs": "DOC",
    }.get(coll, "R")
    from uuid import uuid4
    return f"{prefix}-{uuid4().hex}"


# ── Полная синхронизация состояния ──────────────────────────────────

def get_state(conn) -> dict:
    state = {"version": 3, "serverTime": _now(), "_delta": True, **{coll: [] for coll in COLLECTIONS}}
    placeholders = ",".join("?" for _ in COLLECTIONS)
    rows = conn.execute(
        f"SELECT id, data, updated, coll FROM crm_records WHERE coll IN ({placeholders}) "
        "ORDER BY updated DESC",
        COLLECTIONS,
    ).fetchall()
    for row in rows:
        state[row[3]].append(_row_to_rec(row))
    return state


def put_state(conn, payload: dict) -> dict:
    """Save changed rows only and detect conflicts using server revisions.

    Old clients may still send complete snapshots. Only apply their rows when a
    known revision matches, or when the ID is genuinely new.
    """
    delta = payload.get("_delta") is True
    incoming = []
    for coll in COLLECTIONS:
        items = payload.get(coll, [])
        if not isinstance(items, list):
            raise ValueError(f"Таблица «{coll}»: ожидается список записей")
        seen = set()
        for rec in items:
            if not isinstance(rec, dict) or not rec.get("id"):
                raise ValueError(f"Таблица «{coll}»: у каждой записи должен быть ID")
            rid = _row_id(rec["id"], coll)
            if rid in seen:
                raise ValueError(f"Таблица «{coll}»: ID «{rid}» повторяется")
            seen.add(rid)
            if delta and "_expectedRev" not in rec:
                raise ValueError(f"Запись «{rid}»: отсутствует версия для синхронизации")
            incoming.append((coll, rid, rec))

    conflicts = 0
    with write_transaction(conn) as tx:
        for coll, rid, rec in incoming:
            current = get_record(tx, coll, rid)
            if delta and rec.get("_delete") is True:
                if current is None:
                    continue
                if rec["_expectedRev"] != current["_updatedAt"]:
                    raise ConflictError(coll, rid)
                _remember_deletions(tx, coll, rid)
                tx.execute("DELETE FROM crm_records WHERE coll=? AND id=?", (coll, rid))
                continue
            document = _record_data(rec, rid)
            if current and document == _record_data(current, rid):
                continue  # repeated request after losing a successful response
            rev = (current or {}).get("_updatedAt")
            expected = rec.get("_expectedRev" if delta else "_updatedAt")
            deleted = current is None and get_record(tx, _DELETED_PREFIX + coll, rid)
            if expected != rev or deleted:
                if delta:
                    raise ConflictError(coll, rid)
                conflicts += 1
                continue
            _write(tx, coll, document, rid)
        return {**get_state(tx), "conflicts": conflicts, "_delta": delta}


# ── Массовые операции над таблицами (импорт CSV / сброс данных) ─────

def import_collection(conn, coll: str, records: list, mode: str = "merge") -> dict:
    """Apply the whole file or roll back the entire import."""
    if coll not in COLLECTIONS or mode not in ("merge", "replace"):
        raise ValueError("Неизвестная таблица или режим импорта")
    if not records:
        raise ValueError("Пустой файл: импортировать нечего")

    validated = []
    seen = set()
    for index, rec in enumerate(records, 1):
        if not isinstance(rec, dict):
            raise ValueError(f"Строка {index}: ожидается объект")
        rid = _row_id(rec.get("id"), coll)
        if rid in seen:
            raise ValueError(f"Строка {index}: ID «{rid}» повторяется")
        seen.add(rid)
        validated.append((rid, rec))

    with write_transaction(conn) as tx:
        removed = 0
        if mode == "replace":
            _remember_deletions(tx, coll)
            removed = tx.execute("DELETE FROM crm_records WHERE coll=?", (coll,)).rowcount
        created = updated = 0
        affected = []
        for rid, rec in validated:
            current = get_record(tx, coll, rid)
            expected = rec.get("_expectedRev", _NO_REVISION)
            if expected is not _NO_REVISION and expected != (current or {}).get("_updatedAt"):
                raise ConflictError(coll, rid)
            document = _record_data({**(current or {}), **rec}, rid)
            if current:
                updated += 1
            else:
                created += 1
            affected.append(current if current and document == _record_data(current, rid)
                            else _write(tx, coll, document, rid))
        total = tx.execute("SELECT count(*) FROM crm_records WHERE coll=?", (coll,)).fetchone()[0]
        return {"created": created, "updated": updated, "removed": removed,
                "total": total, "records": affected}


def wipe_collection(conn, coll: str) -> int:
    if coll not in COLLECTIONS:
        raise ValueError(f"Неизвестная коллекция: {coll}")
    with write_transaction(conn) as tx:
        _remember_deletions(tx, coll)
        return tx.execute("DELETE FROM crm_records WHERE coll=?", (coll,)).rowcount


# ── Сборка сквозного процесса (руководство §3) ──────────────────────

def build_process(conn, journey_id: str) -> dict | None:
    j = get_record(conn, "journeys", journey_id)
    if not j:
        return None

    def strip(r):
        return {k: v for k, v in r.items() if k != "_updatedAt"} if r else None

    out = {"journey": strip(j)}
    for key, coll, fid in (
        ("lead", "leads", "leadId"), ("farm", "farms", "farmId"),
        ("deal", "deals", "dealId"), ("pilot", "pilots", "pilotId"),
        ("quote", "quotes", "quoteId"), ("order", "orders", "orderId"),
    ):
        rid = j.get(fid)
        out[key] = strip(get_record(conn, coll, rid)) if rid else None
    inv_id = j.get("invoiceId")
    out["invoice"] = strip(get_record(conn, "invoices", inv_id)) if inv_id else None
    sh_id = j.get("shipmentId")
    out["shipment"] = strip(get_record(conn, "shipments", sh_id)) if sh_id else None
    # связанные задачи (refKind journey/pilots/deal/farm этого маршрута)
    tasks = [t for t in list_records(conn, "tasks")
             if t.get("refId") in {j.get("id"), j.get("dealId"), j.get("pilotId"), j.get("farmId")} - {None}]
    out["tasks"] = [strip(t) for t in tasks]
    # коммуникации по хозяйству — из ленты comms (схема: колонки, не JSON)
    if j.get("farmId"):
        import db as _store
        rows = conn.execute(
            "SELECT * FROM comms WHERE farm_id=? ORDER BY ts DESC LIMIT 50", (j["farmId"],)
        ).fetchall()
        out["comms"] = [_store.to_dict(r) for r in rows]
    else:
        out["comms"] = []
    return out


# ── Интеграция входящих коммуникаций с CRM (руководство §6 «История») ───────

def _digits(s):
    import re as _re
    return _re.sub(r"\D", "", s or "")


def auto_link_tg(conn, handle: str | None, phone: str | None) -> str | None:
    """Привязка входящего Telegram/WhatsApp-сообщения к хозяйству по данным
    реестра CRM (farms + contacts), а не только по snapshot farms.json.

    Совпадение по @username или номеру телефона любого контактного лица либо
    самого хозяйства. Возвращает id хозяйства или None."""
    h = (handle or "").lstrip("@").lower()
    d = _digits(phone)
    if not h and len(d) < 6:
        return None
    for farm in list_records(conn, "farms"):
        f = farm.get("data") if "data" in farm else farm
        if isinstance(f, str):
            continue
        if h and _tg_norm(f.get("telegram")) == h:
            return f.get("id")
        if len(d) >= 6 and _digits(f.get("phone")) == d:
            return f.get("id")
    for c in list_records(conn, "contacts"):
        ct = c.get("data") if "data" in c else c
        if isinstance(ct, str):
            continue
        if h and _tg_norm(ct.get("telegram")) == h:
            return ct.get("farmId")
        if len(d) >= 6 and _digits(ct.get("phone")) == d:
            return ct.get("farmId")
    return None


def _tg_norm(v) -> str:
    return str(v or "").lstrip("@").strip().lower()


def register_comm(conn, item: dict) -> None:
    """Зафиксировать входящую коммуникацию в CRM: создать событие календаря
    и запись истории для связанного хозяйства, при наличии farmId.

    Идемпотентность — по id коммуникации (eventId = comm:<id>)."""
    farm_id = item.get("farmId")
    if not farm_id:
        return
    cid = item.get("id") or ""
    kind_label = {"telegram": "Telegram", "whatsapp": "WhatsApp", "call": "Звонок"}.get(
        item.get("kind"), "Сообщение")
    text = (item.get("text") or item.get("note") or "").strip()
    who = item.get("contact") or item.get("handle") or item.get("phone") or "Неизвестный контакт"
    # событие календаря (§7: события периода открывают связанный объект)
    ev_id = f"comm:{cid}"
    if not get_record(conn, "applications", ev_id):
        upsert(conn, "applications", {
            "id": ev_id,
            "title": f"{kind_label}: {who}",
            "date": (item.get("ts") or "")[:10],
            "time": (item.get("ts") or "")[11:16] or None,
            "kind": "communication",
            "farmId": farm_id,
            "refKind": "farm",
            "refId": farm_id,
            "openObject": {"kind": "comm", "id": cid},
            "summary": text[:280],
            "createdBy": "system:comms",
        }, ev_id)
    # запись в историю клиента (§6)
    note_id = f"hist:{cid}"
    if not get_record(conn, "clientNotes", note_id):
        upsert(conn, "clientNotes", {
            "id": note_id,
            "farmId": farm_id,
            "type": "communication",
            "text": f"Входящее {kind_label} от «{who}»: {text[:280]}",
            "ts": item.get("ts"),
            "commId": cid,
            "createdBy": "system:comms",
        }, note_id)

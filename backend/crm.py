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
  PUT    /api/crm/state                 — полная синхронизация (lastWriteWins по updatedAt)
  GET    /api/crm/{coll}                — список записей коллекции
  POST   /api/crm/{coll}                — создать запись
  PUT    /api/crm/{coll}/{rid}          — заменить запись
  DELETE /api/crm/{coll}/{rid}          — удалить запись
  GET    /api/crm/journeys/{jid}/process— собранный сквозной процесс:
         journey + lead + farm + deal + pilot + quote + order + invoice +
         shipment + tasks (всё, что связано с маршрутом)
"""

import json
import sqlite3
from datetime import datetime, timezone

COLLECTIONS = (
    "farms", "leads", "deals", "journeys", "pilots", "quotes", "orders",
    "invoices", "shipments", "tasks", "contacts", "clientNotes",
    "applications", "payments", "media", "social", "knowledge", "skus",
    "warehouse", "production", "clientDocs",
)

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


def upsert(conn, coll: str, rec: dict, rid: str | None = None) -> dict:
    """Сохранить запись. Опциональный контроль версии (см. put_state):
    expected_rev — сервер отклоняет замену (ConflictError → HTTP 409), если
    текущая серверная метка updated не совпадает с ожидаемой клиентом."""
    rid = rid or rec.get("id") or _gen_id(coll)
    rec = {**rec, "id": rid}
    stamp = _now()
    expected_rev = rec.pop("_expectedRev", None)
    if expected_rev is not None:
        cur = conn.execute(
            "SELECT updated FROM crm_records WHERE coll=? AND id=?", (coll, rid)).fetchone()
        if cur and (cur[0] or "") != expected_rev:
            raise ConflictError(coll, rid)
    conn.execute(
        "INSERT INTO crm_records (id, coll, data, updated) VALUES (?,?,?,?) "
        "ON CONFLICT(coll,id) DO UPDATE SET data=excluded.data, updated=excluded.updated",
        (rid, coll, json.dumps(rec, ensure_ascii=False), stamp),
    )
    conn.commit()
    rec["_updatedAt"] = stamp
    return rec


class ConflictError(Exception):
    """Оптимистичная блокировка: запись изменилась другим пользователем."""

    def __init__(self, coll: str, rid: str):
        super().__init__(f"{coll}/{rid}")
        self.coll, self.rid = coll, rid


def delete(conn, coll: str, rid: str) -> bool:
    cur = conn.execute("DELETE FROM crm_records WHERE coll=? AND id=?", (coll, rid))
    conn.commit()
    return cur.rowcount > 0


def _gen_id(coll: str) -> str:
    prefix = {
        "farms": "F", "leads": "L", "deals": "D", "journeys": "J", "pilots": "P",
        "quotes": "Q", "orders": "O", "invoices": "INV", "shipments": "SH",
        "tasks": "T", "contacts": "CT", "clientNotes": "N", "payments": "PAY",
        "applications": "AP", "clientDocs": "DOC",
    }.get(coll, "R")
    import random
    return f"{prefix}-{int(datetime.now().timestamp()*1000)%10**9}{random.randint(100,999)}"


# ── Полная синхронизация состояния ──────────────────────────────────

def get_state(conn) -> dict:
    state = {"version": 3, "serverTime": _now()}
    for coll in COLLECTIONS:
        state[coll] = list_records(conn, coll)
    return state


def put_state(conn, payload: dict) -> dict:
    """Синхронизация всего снимка с разрешениями конфликтов lastWriteWins.

    Клиент присылает { coll: [records...] } + _syncAt (метка последней
    записи клиента). Сервер для каждой записи сравнивает метки: если клиентская
    свежее или записи на сервере нет — принимаем; иначе возвращаем серверную.

    Удаления стали БЕЗОПАСНЫМИ: запись удаляется только если клиент прислал
    полный снимок коллекции (`_fullSync.collections` содержит имя) ИЛИ в явном
    списке `_deletedRecords`. Раньше любая неполная выгрузка клиента (например,
    коллекция не была загружена локально) молча стирала серверные данные —
    это был главный риск потери данных при lastWriteWins.
    """
    server_stamp = conn.execute("SELECT MAX(updated) FROM crm_records").fetchone()[0] or ""
    client_stamp = payload.get("_syncAt") or ""
    full = payload.get("_fullSync") or {}
    full_colls = set(full.get("collections") or [])
    explicit_deleted = set(payload.get("_deletedRecords") or [])
    result = {"conflicts": 0}
    for coll in COLLECTIONS:
        items = payload.get(coll)
        if not isinstance(items, list):
            result[coll] = list_records(conn, coll)
            continue
        client_ids = set()
        for rec in items:
            rid = rec.get("id")
            if not rid:
                continue
            client_ids.add(rid)
            existing = conn.execute(
                "SELECT updated FROM crm_records WHERE coll=? AND id=?", (coll, rid)
            ).fetchone()
            rec_stamp = rec.get("_updatedAt") or rec.get("updatedAt") or ""
            # если клиент прислал данные раньше/равно серверным — не перетираем,
            # а считаем конфликт: фронт получит серверную версию и обновит UI
            if existing and (existing[0] or "") > rec_stamp and client_stamp <= (existing[0] or ""):
                result["conflicts"] += 1
                continue
            clean = {k: v for k, v in rec.items() if k != "_updatedAt"}
            upsert(conn, coll, clean, rid)
        # удаления: только когда клиент явно синхронизируется позже сервера,
        # и только по полному снимку коллекции или явному списку удалений
        may_delete = client_stamp and client_stamp > server_stamp and (
            coll in full_colls or explicit_deleted)
        if may_delete:
            rows = conn.execute("SELECT id, updated FROM crm_records WHERE coll=?", (coll,)).fetchall()
            for r in rows:
                gone = (r[0] not in client_ids and coll in full_colls) or \
                       (f"{coll}:{r[0]}" in explicit_deleted)
                if gone and (r[1] or "") < client_stamp:
                    conn.execute("DELETE FROM crm_records WHERE coll=? AND id=?", (coll, r[0]))
        conn.commit()
        result[coll] = list_records(conn, coll)
    return {"version": 3, "serverTime": _now(), **result}


# ── Массовые операции над таблицами (импорт CSV / сброс данных) ─────

def import_collection(conn, coll: str, records: list, mode: str = "merge") -> dict:
    """Массовая загрузка записей коллекции из внешнего источника (CSV-импорт
    во фронтенде). Режимы:
      merge  — апсерт по id (или генерация нового id), существующие не затираются
               пустыми значениями;
      replace — сначала полное удаление коллекции, затем загрузка.
    Возвращает {'created', 'updated', 'total'}.
    """
    if coll not in COLLECTIONS:
        raise ValueError(f"Неизвестная коллекция: {coll}")
    removed = 0
    if mode == "replace":
        cur = conn.execute("DELETE FROM crm_records WHERE coll=?", (coll,))
        removed = cur.rowcount
    created = updated = 0
    for raw in records or []:
        if not isinstance(raw, dict):
            continue
        rec = {k: v for k, v in raw.items() if k not in ("_updatedAt", "_expectedRev")}
        rid = rec.get("id")
        if rid and get_record(conn, coll, rid):
            existing = get_record(conn, coll, rid)
            merged = {**existing, **rec, "id": rid}
            upsert(conn, coll, merged, rid)
            updated += 1
        else:
            upsert(conn, coll, rec, rid or None)
            created += 1
    conn.commit()
    return {"created": created, "updated": updated, "removed": removed,
            "total": len(list_records(conn, coll))}


def wipe_collection(conn, coll: str) -> int:
    """Полностью очистить одну таблицу CRM. Возвращает число удалённых записей."""
    if coll not in COLLECTIONS:
        raise ValueError(f"Неизвестная коллекция: {coll}")
    cur = conn.execute("DELETE FROM crm_records WHERE coll=?", (coll,))
    conn.commit()
    return cur.rowcount


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

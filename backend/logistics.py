"""Логистика: поставки и выгрузки (отгрузки) товара.

REST-хранение для раздела «Логистика» фронтенда (ShipmentsView.vue):
  * supply   — поставка (приход на склад): от кого, что, сколько, по какой цене;
  * dispatch — выгрузка/отгрузка товара клиенту со склада.

Документ = шапка (реквизиты) + позиции (items). По документу можно создать
«акт под документы» (act): Акт приёма-передачи / ТОРГ-12 / накладная — поле act
хранит выпущенный акт (тип, номер, дата); повторная генерация перезаписывает.

Хранилище — PostgreSQL (таблица logistics_docs; legacy-режим SQLite), чтобы все
сотрудники видели общие данные.
"""

import json
import sqlite3
from datetime import datetime, timezone

SCHEMA_LOGISTICS = """
CREATE TABLE IF NOT EXISTS logistics_docs (
    id      TEXT PRIMARY KEY,
    kind    TEXT NOT NULL CHECK (kind IN ('supply','dispatch')),
    data    TEXT NOT NULL,
    updated TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_log_kind ON logistics_docs (kind, updated DESC);
"""

KINDS = ("supply", "dispatch")


def init_tables(conn) -> None:
    """В postgres-режиме схема создаётся schema.sql — здесь только SQLite."""
    import db as _store
    if _store.IS_POSTGRES:
        return
    conn.executescript(SCHEMA_LOGISTICS)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_doc(row) -> dict:
    d = json.loads(row[1])
    d["id"] = row[0]
    d["kind"] = row[2]
    d["updatedAt"] = row[3]
    return d


def list_docs(conn, kind: str | None = None) -> list[dict]:
    if kind:
        rows = conn.execute(
            "SELECT id, data, kind, updated FROM logistics_docs WHERE kind=? ORDER BY updated DESC",
            (kind,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, data, kind, updated FROM logistics_docs ORDER BY updated DESC"
        ).fetchall()
    return [_row_to_doc(r) for r in rows]


def get_doc(conn, doc_id: str) -> dict | None:
    row = conn.execute(
        "SELECT id, data, kind, updated FROM logistics_docs WHERE id=?", (doc_id,)
    ).fetchone()
    return _row_to_doc(row) if row else None


def normalize_doc(body: dict, doc_id: str) -> dict:
    """Приводим payload фронтенда к каноничному виду."""
    items_in = body.get("items") or []
    items = []
    for i, it in enumerate(items_in):
        items.append({
            "skuId": str(it.get("skuId") or ""),
            "name": str(it.get("name") or ""),
            "qty": float(it.get("qty") or 0),
            "unit": str(it.get("unit") or "л"),
            "price": float(it.get("price") or 0),
            "note": str(it.get("note") or ""),
        })
    doc = {
        "id": doc_id,
        "number": str(body.get("number") or ""),
        "date": str(body.get("date") or _now()[:10]),
        "status": str(body.get("status") or "Черновик"),
        "party": str(body.get("party") or ""),          # поставщик / получатель
        "farmId": body.get("farmId") or None,           # привязка к хозяйству (для отгрузок)
        "orderId": body.get("orderId") or None,         # привязка к заказу
        "warehouse": str(body.get("warehouse") or ""),
        "vehicle": str(body.get("vehicle") or ""),      # транспорт (отгрузка)
        "driver": str(body.get("driver") or ""),        # водитель/экспедитор
        "base": str(body.get("base") or ""),            # основание (договор/заявка)
        "note": str(body.get("note") or ""),
        "act": body.get("act") or None,                 # {"type","number","date"} — выпущенный акт
        "items": items,
    }
    return doc


def upsert_doc(conn, body: dict, doc_id: str) -> dict:
    kind = body.get("kind") or "supply"
    if kind not in KINDS:
        raise ValueError(f"kind должен быть одним из {KINDS}")
    doc = normalize_doc(body, doc_id)
    now = _now()
    conn.execute(
        """INSERT INTO logistics_docs (id, kind, data, updated)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET kind=excluded.kind, data=excluded.data, updated=excluded.updated""",
        (doc_id, kind, json.dumps(doc, ensure_ascii=False), now),
    )
    conn.commit()
    doc["updatedAt"] = now
    return doc


def delete_doc(conn, doc_id: str) -> bool:
    cur = conn.execute("DELETE FROM logistics_docs WHERE id=?", (doc_id,))
    conn.commit()
    return cur.rowcount > 0

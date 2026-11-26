"""Document-based stock accounting. BIGINT stores exact decimal(15,4) on both databases."""

from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request

import crm
import db

router = APIRouter(prefix="/api")
SCALE = 10000
MAX = 10**15 - 1
TYPES = {"purchase", "sale", "move", "writeoff", "production", "inventory", "return"}
CATALOG = {"products": "stock_products", "warehouses": "stock_warehouses", "recipes": "stock_recipes"}
QUANTITIES = {"qty", "unit_cost", "min_stock_alert", "output_qty_per_batch", "qty_per_unit_output"}


def init_tables(conn):
    conn.executescript((Path(__file__).parent / "migrations/001_stock.sql").read_text())
    with crm.write_transaction(conn) as tx:
        marker = tx.execute("INSERT INTO stock_migrations(version) VALUES (1) ON CONFLICT DO NOTHING RETURNING version").fetchone()
        if marker:
            tx.executemany("INSERT INTO stock_warehouses(id,name,is_virtual) VALUES (?,?,?) ON CONFLICT DO NOTHING", [
                ("raw", "Склад сырья", 0), ("packaging", "Склад тары", 0),
                ("finished", "Склад готовой продукции", 0), ("reject", "Брак", 1),
            ])


def now():
    return datetime.now(timezone.utc).isoformat()


def fail(message, status=422):
    raise HTTPException(status, message)


def fixed(value):
    try:
        dec = Decimal(str(value))
        scaled = dec * SCALE
        if dec.is_finite() and 0 <= scaled <= MAX and scaled == scaled.to_integral_value():
            return int(scaled)
    except (InvalidOperation, ValueError):
        pass
    fail("Количество или цена должны быть неотрицательными, до 11 целых и 4 дробных знаков.")


def rounded(numerator, denominator):
    return int((Decimal(numerator) / Decimal(denominator)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def decimal(value):
    return format(Decimal(value) / SCALE, ".4f")


def present(row):
    return {key: decimal(value) if key in QUANTITIES and value is not None else value
            for key, value in dict(row).items()}


def required(value, label):
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        fail(f"Укажите «{label}» (до 200 символов).")
    return value.strip()


def get(conn, table, rid):
    if not isinstance(rid, str) or not rid:
        fail("Выберите складскую запись.")
    row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (rid,)).fetchone()
    if row is None:
        fail("Складская запись не найдена.", 404)
    return dict(row)


def save(conn, table, row, exists=False):
    names = tuple(row)
    if exists:
        fields = tuple(name for name in names if name != "id")
        assignments = ",".join(f"{name}=?" for name in fields)
        conn.execute(f"UPDATE {table} SET {assignments} WHERE id=?",
                     (*[row[name] for name in fields], row["id"]))
    else:
        marks = ",".join("?" for _ in names)
        conn.execute(f"INSERT INTO {table} ({','.join(names)}) VALUES ({marks})", tuple(row.values()))


def write_allowed(request, production=False):
    if request.state.user == "worker" or not (request.state.role in {"director", "operations", "warehouse"} or
                                            production and request.state.role == "production"):
        fail("Нет доступа к проведению и настройке склада.", 403)


def stock_product(conn, rid):
    row = get(conn, "stock_products", rid)
    if row["type"] == "service":
        fail(f"Услуга «{row['name']}» не имеет складских остатков.")
    return row


def totals(conn, warehouse, product):
    row = conn.execute("SELECT COALESCE(SUM(qty),0) AS quantity, COALESCE(SUM(value_delta),0) AS valuation FROM stock_movements "
                       "WHERE warehouse_id=? AND product_id=?", (warehouse, product)).fetchone()
    return int(row[0]), int(row[1])


def reservation_rows(conn, warehouse, product):
    return [dict(row) for row in conn.execute(
        "SELECT r.*, r.qty-COALESCE(SUM(CASE WHEN d.status='conducted' THEN u.qty ELSE 0 END),0) AS remaining "
        "FROM stock_reservations r LEFT JOIN stock_reservation_usage u ON r.id=u.reservation_id "
        "LEFT JOIN stock_documents d ON d.id=u.document_id "
        "WHERE r.warehouse_id=? AND r.product_id=? AND r.expires_at>? "
        "GROUP BY r.id,r.product_id,r.warehouse_id,r.order_id,r.qty,r.expires_at ORDER BY r.expires_at,r.id",
        (warehouse, product, now())).fetchall()]


def reserved(conn, warehouse, product, except_order=None):
    return sum(int(row["remaining"]) for row in reservation_rows(conn, warehouse, product)
               if except_order is None or row["order_id"] != except_order)


def average(quantity, value):
    return max(0, rounded(value * SCALE, quantity)) if quantity > 0 else 0


def recipe_items(conn, rid):
    return [dict(row) for row in conn.execute(
        "SELECT * FROM stock_recipe_items WHERE recipe_id=? ORDER BY warehouse_id,component_product_id", (rid,))]


def list_items(conn, table, field, rid):
    return [present(row) for row in conn.execute(f"SELECT * FROM {table} WHERE {field}=? ORDER BY id", (rid,))]


def catalog_row(conn, kind, rid):
    row = present(get(conn, CATALOG[kind], rid))
    if kind == "recipes":
        row["items"] = list_items(conn, "stock_recipe_items", "recipe_id", rid)
    return row


def put_catalog(tx, kind, raw, rid=None):
    table = CATALOG[kind]
    previous = get(tx, table, rid) if rid else None
    row = {"id": rid or uuid4().hex}
    if kind == "products":
        row.update(sku=required(raw.get("sku"), "Артикул"), name=required(raw.get("name"), "Название"),
                   unit=raw.get("unit"), type=raw.get("type"), min_stock_alert=fixed(raw.get("min_stock_alert", 0)))
        if row["unit"] not in {"шт", "кг", "л"} or row["type"] not in {"raw", "packaging", "finished", "service"}:
            fail("Выберите тип товара и единицу измерения.")
        if previous and any(row[k] != previous[k] for k in ("unit", "type")):
            if any(tx.execute(f"SELECT 1 FROM {t} WHERE {col}=? LIMIT 1", (rid,)).fetchone()
                   for t, col in (("stock_document_items", "product_id"), ("stock_movements", "product_id"),
                                  ("stock_reservations", "product_id"), ("stock_recipe_items", "component_product_id"),
                                  ("stock_recipes", "output_product_id"))):
                fail("Тип и единицу использованного товара менять нельзя.", 409)
    elif kind == "warehouses":
        row.update(name=required(raw.get("name"), "Название"), is_virtual=int(raw.get("is_virtual") is True),
                   allow_negative=int(raw.get("allow_negative") is True))
        if not row["allow_negative"] and tx.execute(
            "SELECT 1 FROM stock_movements WHERE warehouse_id=? GROUP BY product_id HAVING SUM(qty)<0", (rid,)
        ).fetchone():
            fail("Сначала закройте отрицательные остатки.", 409)
    else:
        row.update(output_product_id=raw.get("output_product_id"),
                   output_qty_per_batch=fixed(raw.get("output_qty_per_batch", 1)),
                   version=required(raw.get("version"), "Версия"), is_active=int(raw.get("is_active") is True))
        if stock_product(tx, row["output_product_id"])["type"] != "finished" or not row["output_qty_per_batch"]:
            fail("Техкарта требует готовый продукт и положительный выпуск партии.")
        incoming = raw.get("items")
        if not isinstance(incoming, list) or not incoming or len(incoming) > 100 or any(not isinstance(item, dict) for item in incoming):
            fail("Добавьте от 1 до 100 компонентов.")
        items = []
        for item in incoming:
            p = stock_product(tx, item.get("component_product_id"))
            w = get(tx, "stock_warehouses", item.get("warehouse_id"))
            qty = fixed(item.get("qty_per_unit_output"))
            if p["type"] not in {"raw", "packaging"} or not qty:
                fail("Компонент должен быть сырьём или тарой с положительным расходом.")
            items.append(dict(id=uuid4().hex, recipe_id=row["id"], component_product_id=p["id"],
                              warehouse_id=w["id"], qty_per_unit_output=qty))
        if previous and tx.execute("SELECT 1 FROM stock_documents WHERE recipe_id=? LIMIT 1", (rid,)).fetchone():
            keys = ("component_product_id", "warehouse_id", "qty_per_unit_output")
            if (any(previous[k] != row[k] for k in ("output_product_id", "output_qty_per_batch", "version"))
                or sorted(tuple(i[k] for k in keys) for i in items) !=
                sorted(tuple(i[k] for k in keys) for i in recipe_items(tx, rid))):
                fail("Эта версия используется в документах. Создайте новую версию.", 409)
        if row["is_active"]:
            tx.execute("UPDATE stock_recipes SET is_active=0 WHERE output_product_id=? AND id<>?",
                       (row["output_product_id"], row["id"]))
        save(tx, table, row, bool(previous))
        tx.execute("DELETE FROM stock_recipe_items WHERE recipe_id=?", (row["id"],))
        for item in items:
            save(tx, "stock_recipe_items", item)
        return catalog_row(tx, kind, row["id"])
    save(tx, table, row, bool(previous))
    return catalog_row(tx, kind, row["id"])


def guard_source(tx, collection, record_id=None):
    if collection not in {"logistics", "production", "shipments", "orders"}:
        return
    predicate = " AND source_id=?" if record_id else ""
    args = (collection, record_id) if record_id else (collection,)
    if tx.execute("SELECT 1 FROM stock_documents WHERE status='conducted' AND source_collection=?"
                  + predicate + " LIMIT 1", args).fetchone():
        fail("Запись связана с проведённым складским документом. Сначала сделайте сторно в разделе «Склад».", 409)


def document(tx, rid):
    return {**present(get(tx, "stock_documents", rid)),
            "items": list_items(tx, "stock_document_items", "document_id", rid)}


def validate_source(tx, row):
    kind = row["doc_type"]
    source_kind = {("production", "production"), ("purchase", "logistics"),
                   ("sale", "logistics"), ("sale", "shipments"), ("sale", "orders")}
    if row["source_id"] or row["source_collection"]:
        if not row["source_id"] or (kind, row["source_collection"]) not in source_kind:
            fail("Некорректный вид документа-основания.")
        if row["source_collection"] == "logistics":
            exists = tx.execute("SELECT 1 FROM logistics_docs WHERE id=?", (row["source_id"],)).fetchone()
        else:
            exists = crm.get_record(tx, row["source_collection"], row["source_id"])
        if not exists:
            fail("Документ-основание не найден.")


def put_document(tx, raw, actor, rid=None):
    previous = get(tx, "stock_documents", rid) if rid else None
    if previous and previous["status"] != "draft":
        fail("Редактировать можно только черновик.", 409)
    kind = raw.get("doc_type")
    if kind not in TYPES:
        fail("Выберите тип документа.")
    rid = rid or uuid4().hex
    row = dict(id=rid, doc_type=kind, number=required(raw.get("number") or f"{kind.upper()}-{rid[:10]}", "Номер"),
               status="draft", created_by=previous["created_by"] if previous else actor)
    for key in ("warehouse_from_id", "warehouse_to_id", "recipe_id", "order_id", "counterparty_id", "source_collection", "source_id"):
        row[key] = raw.get(key) or None
    for field, coll in (("order_id", "orders"), ("counterparty_id", "farms")):
        if row[field] and not crm.get_record(tx, coll, row[field]):
            fail("Связанная запись CRM не найдена.")
    validate_source(tx, row)
    source, target = row["warehouse_from_id"], row["warehouse_to_id"]
    if kind in {"sale", "move", "writeoff"} and not source or kind in {"purchase", "return", "move", "production", "inventory"} and not target:
        fail("Выберите склады документа.")
    if kind == "move" and source == target:
        fail("Склады перемещения должны отличаться.")
    if kind == "production":
        get(tx, "stock_recipes", row["recipe_id"])
    else:
        row["recipe_id"] = None
    items = raw.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= 100 or any(not isinstance(item, dict) for item in items):
        fail("Добавьте от 1 до 100 позиций.")
    save(tx, "stock_documents", row, bool(previous))
    tx.execute("DELETE FROM stock_document_items WHERE document_id=?", (rid,))
    for item in items:
        product = stock_product(tx, item.get("product_id"))
        qty = fixed(item.get("qty"))
        if qty == 0 and kind != "inventory":
            fail("Количество должно быть больше нуля.")
        cost = item.get("unit_cost")
        save(tx, "stock_document_items", dict(id=uuid4().hex, document_id=rid, product_id=product["id"],
                                                qty=qty, unit_cost=None if cost in ("", None) else fixed(cost)))
    return document(tx, rid)


def movement(tx, doc, product, warehouse, change, value=None, reversal=None, unit_cost=None):
    if not change:
        return 0
    physical, current_value = totals(tx, warehouse, product)
    if change < 0:
        others = reserved(tx, warehouse, product, doc["order_id"] if doc["doc_type"] == "sale" and not reversal else None)
        free = physical - others
        if free + change < 0 and (others or (doc["doc_type"] == "production" and not reversal) or
                                  not get(tx, "stock_warehouses", warehouse)["allow_negative"]):
            name = stock_product(tx, product)["name"]
            fail(f"Недостаточно «{name}» на складе. Не хватает {decimal(-change-free)}.", 409)
    if value is None:
        value = -current_value if physical + change == 0 else (rounded(change * current_value, physical) if physical > 0 else 0)
    recorded_value = value
    if physical < 0 and change > 0 and not reversal:
        filled = min(change, -physical)
        value = rounded(-current_value * filled, -physical) + rounded(value * (change-filled), change)
    if physical + change >= 0 and (current_value + value < 0 or (physical + change == 0 and current_value + value != 0)):
        fail("Движение нарушит оценку остатков. Сначала отмените зависимые документы.", 409)
    if abs(physical + change) > MAX or abs(value) > MAX or abs(current_value + value) > MAX:
        fail("Превышена точность складского количества или стоимости.")
    save(tx, "stock_movements", dict(id=uuid4().hex, product_id=product, warehouse_id=warehouse,
         qty=change, unit_cost=unit_cost if unit_cost is not None else rounded(abs(recorded_value) * SCALE, abs(change)), value_delta=value,
         document_id=doc["id"], moved_at=now(), reversal_of=reversal))
    return value


def consume_reserve(tx, doc, warehouse, product, qty):
    if not doc["order_id"]:
        return
    for item in reservation_rows(tx, warehouse, product):
        if item["order_id"] != doc["order_id"] or not qty or item["remaining"] <= 0:
            continue
        used = min(qty, item["remaining"])
        tx.execute("INSERT INTO stock_reservation_usage(document_id,reservation_id,qty) VALUES (?,?,?)",
                   (doc["id"], item["id"], used))
        qty -= used


def transition(tx, rid, action):
    doc = get(tx, "stock_documents", rid)
    status = doc["status"]
    if action == "cancel":
        if status == "cancelled":
            return document(tx, rid)
        if status == "conducted":
            rows = tx.execute("SELECT * FROM stock_movements WHERE document_id=? AND reversal_of IS NULL "
                              "ORDER BY moved_at DESC,id DESC", (rid,)).fetchall()
            for row in rows:
                movement(tx, doc, row["product_id"], row["warehouse_id"], -row["qty"],
                         -row["value_delta"], row["id"], row["unit_cost"])
            used = tx.execute("SELECT r.* FROM stock_reservations r JOIN stock_reservation_usage u "
                              "ON r.id=u.reservation_id WHERE u.document_id=? AND r.expires_at>?", (rid, now())).fetchall()
            for row in used:
                physical, _ = totals(tx, row["warehouse_id"], row["product_id"])
                usage = tx.execute("SELECT qty FROM stock_reservation_usage WHERE document_id=? AND reservation_id=?",
                                   (rid, row["id"])).fetchone()[0]
                if physical < reserved(tx, row["warehouse_id"], row["product_id"]) + usage:
                    fail("Сторно восстановит резерв сверх остатка. Освободите резерв или пополните склад.", 409)
        tx.execute("UPDATE stock_documents SET status='cancelled',cancelled_at=? WHERE id=?", (now(), rid))
        return document(tx, rid)
    if status == "conducted":
        return document(tx, rid)
    if status != "draft":
        fail("Провести можно только черновик.", 409)
    validate_source(tx, doc)
    kind, source, target = doc["doc_type"], doc["warehouse_from_id"], doc["warehouse_to_id"]
    lines = tx.execute("SELECT * FROM stock_document_items WHERE document_id=?", (rid,)).fetchall()
    if kind == "production":
        recipe = get(tx, "stock_recipes", doc["recipe_id"])
        if len(lines) != 1 or lines[0]["product_id"] != recipe["output_product_id"]:
            fail("Укажите выпуск одного товара из выбранной техкарты.")
        output = lines[0]["qty"]
        value = 0
        for item in recipe_items(tx, recipe["id"]):
            qty = (item["qty_per_unit_output"] * output + SCALE - 1) // SCALE
            value -= movement(tx, doc, item["component_product_id"], item["warehouse_id"], -qty)
        movement(tx, doc, recipe["output_product_id"], target, output, value)
    else:
        for item in lines:
            p, qty, cost = item["product_id"], item["qty"], item["unit_cost"]
            if kind in {"purchase", "return"}:
                if cost is None:
                    fail("Укажите себестоимость прихода, включая нулевую при необходимости.")
                movement(tx, doc, p, target, qty, rounded(qty * cost, SCALE), unit_cost=cost)
            elif kind == "inventory":
                physical, current_value = totals(tx, target, p)
                delta = qty - physical
                if delta > 0 and physical <= 0 and cost is None:
                    fail("Для излишка без текущей оценки укажите себестоимость.")
                valuation = rounded(delta * (cost if cost is not None else average(physical, current_value)), SCALE) if delta > 0 else None
                movement(tx, doc, p, target, delta, valuation, unit_cost=cost if delta > 0 else None)
            else:
                value = movement(tx, doc, p, source, -qty)
                if kind == "move":
                    movement(tx, doc, p, target, qty, -value)
                elif kind == "sale":
                    consume_reserve(tx, doc, source, p, qty)
    tx.execute("UPDATE stock_documents SET status='conducted',conducted_at=? WHERE id=?", (now(), rid))
    return document(tx, rid)


def catalog_table(kind):
    if kind not in CATALOG:
        fail("Справочник не найден.", 404)
    return CATALOG[kind]


def mutation(request, operation, production=False):
    write_allowed(request, production)
    try:
        with closing(db.connect()) as conn, crm.write_transaction(conn) as tx:
            return operation(tx)
    except Exception as exc:
        if type(exc).__name__ in {"IntegrityError", "UniqueViolation", "ForeignKeyViolation", "CheckViolation"}:
            fail("Дублирующаяся позиция или связанная запись. Проверьте данные и связи.", 409)
        raise


@router.get("/stock/catalog/{kind}")
def list_catalog(kind: str):
    table = catalog_table(kind)
    with closing(db.connect()) as conn:
        ids = conn.execute(f"SELECT id FROM {table} ORDER BY id").fetchall()
        return [catalog_row(conn, kind, row[0]) for row in ids]


@router.get("/stock/catalog/{kind}/{rid}")
def read_catalog(kind: str, rid: str):
    catalog_table(kind)
    with closing(db.connect()) as conn:
        return catalog_row(conn, kind, rid)


@router.post("/stock/catalog/{kind}", status_code=201)
def create_catalog(kind: str, body: dict, request: Request):
    catalog_table(kind)
    return mutation(request, lambda tx: put_catalog(tx, kind, body))


@router.post("/stock/import-sku/{sku}")
def import_sku(sku: str, body: dict, request: Request):
    def run(tx):
        row = crm.get_record(tx, "skus", sku)
        if not row:
            fail("Артикул CRM не найден.", 404)
        existing = tx.execute("SELECT id FROM stock_products WHERE sku=?", (sku,)).fetchone()
        if existing:
            return catalog_row(tx, "products", existing[0])
        return put_catalog(tx, "products", {**body, "sku": sku, "name": row.get("name") or sku})
    return mutation(request, run)


@router.put("/stock/catalog/{kind}/{rid}")
def update_catalog(kind: str, rid: str, body: dict, request: Request):
    catalog_table(kind)
    return mutation(request, lambda tx: put_catalog(tx, kind, body, rid))


@router.delete("/stock/catalog/{kind}/{rid}")
def remove_catalog(kind: str, rid: str, request: Request):
    table = catalog_table(kind)
    def run(tx):
        get(tx, table, rid)
        if kind == "warehouses":
            import logistics
            related = (*crm.list_records(tx, "production"), *crm.list_records(tx, "shipments"), *logistics.list_docs(tx))
            if any(record.get("warehouseId") == rid for record in related):
                fail("Склад указан в производстве, поставке или отгрузке. Сначала измените эти записи.", 409)
        tx.execute(f"DELETE FROM {table} WHERE id=?", (rid,))
        return {"deleted": True}
    return mutation(request, run)


@router.get("/recipes/{rid}/can_produce")
def can_produce(rid: str):
    with closing(db.connect()) as conn:
        recipe = get(conn, "stock_recipes", rid)
        limits = []
        for item in recipe_items(conn, rid):
            warehouse, product = item["warehouse_id"], item["component_product_id"]
            available = totals(conn, warehouse, product)[0] - reserved(conn, warehouse, product)
            limits.append({**present(item), "available": decimal(available),
                           "output": max(0, available * SCALE // item["qty_per_unit_output"])})
        qty = min((item.pop("output") for item in limits), default=0)
        return {"qty": decimal(qty), "batches": qty // recipe["output_qty_per_batch"], "components": limits}


@router.get("/stock/documents")
def documents(warehouse_id: str | None = None):
    where = (" WHERE warehouse_from_id=? OR warehouse_to_id=? OR EXISTS "
             "(SELECT 1 FROM stock_recipe_items i WHERE i.recipe_id=stock_documents.recipe_id "
             "AND i.warehouse_id=?)") if warehouse_id else ""
    args = (warehouse_id,) * 3 if warehouse_id else ()
    with closing(db.connect()) as conn:
        return [present(row) for row in conn.execute(
            "SELECT * FROM stock_documents" + where + " ORDER BY conducted_at DESC,number", args)]


@router.get("/stock/documents/{rid}")
def read_document(rid: str):
    with closing(db.connect()) as conn:
        return document(conn, rid)


@router.post("/stock/documents", status_code=201)
def create_document(body: dict, request: Request):
    return mutation(request, lambda tx: put_document(tx, body, request.state.user), body.get("doc_type") == "production")


@router.put("/stock/documents/{rid}")
def update_document(rid: str, body: dict, request: Request):
    def run(tx):
        previous = get(tx, "stock_documents", rid)
        write_allowed(request, production=previous["doc_type"] == body.get("doc_type") == "production")
        return put_document(tx, body, request.state.user, rid)
    return mutation(request, run, production=True)


@router.delete("/stock/documents/{rid}")
def delete_document(rid: str, request: Request):
    def run(tx):
        doc = get(tx, "stock_documents", rid)
        write_allowed(request, production=doc["doc_type"] == "production")
        if doc["status"] != "draft":
            fail("Удалить можно только черновик. Для проведённого документа используйте сторно.", 409)
        tx.execute("DELETE FROM stock_documents WHERE id=?", (rid,))
        return {"deleted": True}
    return mutation(request, run, production=True)


@router.post("/stock/documents/{rid}/{action}")
def post_document(rid: str, action: str, request: Request):
    if action not in {"conduct", "cancel"}:
        fail("Действие не найдено.", 404)
    def run(tx):
        write_allowed(request, production=get(tx, "stock_documents", rid)["doc_type"] == "production")
        return transition(tx, rid, action)
    return mutation(request, run, production=True)


def filters(warehouse_id, product_id, date_from=None, date_to=None):
    pairs = [(key, value) for key, value in (("warehouse_id=?", warehouse_id), ("product_id=?", product_id),
             ("moved_at>=?", date_from), ("moved_at<?", date_to)) if value]
    return (" WHERE " + " AND ".join(key for key, _ in pairs) if pairs else ""), tuple(v for _, v in pairs)


@router.get("/stock/balances")
def balances(warehouse_id: str | None = None, product_id: str | None = None):
    with closing(db.connect()) as conn:
        result = []
        for warehouse in conn.execute("SELECT * FROM stock_warehouses ORDER BY name").fetchall():
            w = warehouse["id"]
            if warehouse_id and w != warehouse_id:
                continue
            rows = conn.execute("SELECT product_id,SUM(qty) AS quantity,SUM(value_delta) AS valuation FROM stock_movements "
                                "WHERE warehouse_id=? GROUP BY product_id", (w,)).fetchall()
            amounts = {row[0]: (int(row[1]), int(row[2])) for row in rows}
            for p in conn.execute("SELECT * FROM stock_products WHERE type<>'service' ORDER BY name").fetchall():
                if product_id and product_id != p["id"]:
                    continue
                quantity, value = amounts.get(p["id"], (0, 0))
                hold = reserved(conn, w, p["id"]) if quantity > 0 else 0
                default = {"raw": "raw", "packaging": "packaging", "finished": "finished"}[p["type"]]
                alert = quantity - hold < p["min_stock_alert"] and (p["id"] in amounts or w == default)
                if p["id"] not in amounts and not alert and not (warehouse_id or product_id):
                    continue
                result.append(dict(warehouse_id=w, warehouse=warehouse["name"], product_id=p["id"], product=p["name"],
                                   sku=p["sku"], unit=p["unit"], qty=decimal(quantity), reserved=decimal(hold),
                                   available=decimal(quantity-hold), unit_cost=decimal(average(quantity,value)), low=alert))
        return result


@router.get("/stock/movements")
def movements(warehouse_id: str | None = None, product_id: str | None = None,
              date_from: str | None = None, date_to: str | None = None, limit: int = 200, offset: int = 0):
    where, args = filters(warehouse_id, product_id, date_from, date_to)
    with closing(db.connect()) as conn:
        return [present(row) for row in conn.execute(
            "SELECT * FROM stock_movements" + where + " ORDER BY moved_at DESC,id DESC LIMIT ? OFFSET ?",
            (*args, min(max(1, limit), 1000), max(0, offset)))]


@router.get("/stock/turnover")
def turnover(warehouse_id: str | None = None, product_id: str | None = None,
             date_from: str | None = None, date_to: str | None = None):
    where, args = filters(warehouse_id, product_id, date_from, date_to)
    with closing(db.connect()) as conn:
        return [dict(warehouse_id=row[0], product_id=row[1], receipt=decimal(row[2]), issue=decimal(row[3]))
                for row in conn.execute("SELECT warehouse_id,product_id,SUM(CASE WHEN qty>0 THEN qty ELSE 0 END) AS receipt,"
                                        "SUM(CASE WHEN qty<0 THEN -qty ELSE 0 END) AS issue FROM stock_movements" + where +
                                        " GROUP BY warehouse_id,product_id ORDER BY warehouse_id,product_id", args)]


@router.get("/stock/reservations")
def reservations(warehouse_id: str | None = None):
    with closing(db.connect()) as conn:
        pairs = conn.execute("SELECT DISTINCT warehouse_id,product_id FROM stock_reservations WHERE expires_at>?", (now(),)).fetchall()
        return [{**present(row), "remaining": decimal(row["remaining"]),
                 "editable": not bool(conn.execute(
                     "SELECT 1 FROM stock_reservation_usage WHERE reservation_id=? LIMIT 1", (row["id"],)
                 ).fetchone())}
                for w, p in ((row[0], row[1]) for row in pairs if not warehouse_id or row[0] == warehouse_id)
                for row in reservation_rows(conn, w, p) if row["remaining"] > 0]


@router.post("/stock/reservations", status_code=201)
def reserve(body: dict, request: Request):
    return save_reservation(body, request)


@router.put("/stock/reservations/{rid}")
def update_reservation(rid: str, body: dict, request: Request):
    return save_reservation(body, request, rid)


def save_reservation(body, request, rid=None):
    def run(tx):
        previous = get(tx, "stock_reservations", rid) if rid else None
        if previous and tx.execute("SELECT 1 FROM stock_reservation_usage WHERE reservation_id=? LIMIT 1", (rid,)).fetchone():
            fail("Этот резерв уже участвовал в проведении. Снимите остаток резерва и создайте новый.", 409)
        product = stock_product(tx, body.get("product_id"))["id"]
        warehouse = get(tx, "stock_warehouses", body.get("warehouse_id"))["id"]
        order = required(body.get("order_id"), "Заказ")
        if not crm.get_record(tx, "orders", order):
            fail("Заказ CRM не найден.", 404)
        qty = fixed(body.get("qty"))
        try:
            expiry = datetime.fromisoformat(body.get("expires_at", ""))
            if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
                raise ValueError()
        except (TypeError, ValueError):
            fail("Укажите будущий срок резерва с часовым поясом.")
        reclaimed = (previous["qty"] if previous and previous["expires_at"] > now() and
             previous["warehouse_id"] == warehouse and previous["product_id"] == product else 0)
        if not qty or qty > totals(tx, warehouse, product)[0] - reserved(tx, warehouse, product) + reclaimed:
            fail("Для резерва недостаточно доступного остатка.", 409)
        row = dict(id=rid or uuid4().hex, product_id=product, warehouse_id=warehouse, order_id=order, qty=qty,
                   expires_at=expiry.astimezone(timezone.utc).isoformat())
        save(tx, "stock_reservations", row, bool(previous))
        return present(row)
    return mutation(request, run)


@router.delete("/stock/reservations/{rid}")
def unreserve(rid: str, request: Request):
    def run(tx):
        get(tx, "stock_reservations", rid)
        tx.execute("UPDATE stock_reservations SET expires_at=? WHERE id=? AND expires_at>?", (now(), rid, now()))
        return {"released": True}
    return mutation(request, run)

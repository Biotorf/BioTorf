"""Transactional stock ledger, separate from editable CRM records."""

import hashlib
import json
import re
from uuid import uuid4
from decimal import Decimal, InvalidOperation

import crm
import logistics

RAW_SKUS = frozenset({"POWDER", "PASTE"})
EVENTS = "inventoryEvents"
BALANCES = "inventoryBalances"
SOURCE_POSTINGS = "inventorySourcePostings"
ORDER_STOCK = "inventoryOrderStock"
CANCELLED = {"Отменён", "Отменен", "Отменена", "Отменено"}
TYPES = frozenset({
    "opening", "receipt_paste", "receipt_powder", "receipt_goods", "production", "production_recipe", "reserve", "release",
    "dispatch", "return", "adjustment", "reversal",
})
RECEIPT_TYPES = {"receipt_paste": "paste", "receipt_powder": "powder", "receipt_goods": ""}
SOURCE_TYPES = {
    "receipt_goods": {"logistics"},
    "receipt_paste": {"logistics"},
    "receipt_powder": {"logistics"},
    "production": {"production"},
    "production_recipe": {"production"},
    "reserve": {"orders"},
    "release": {"orders"},
    "dispatch": {"shipments", "logistics"},
    "return": {"shipments", "logistics"},
}


class InventoryConflict(ValueError):
    """Another posting already consumed, reserved or claimed this stock."""


def may_post(role: str, event_type: str) -> bool:
    if event_type == "production_recipe":
        return False
    return role in {"director", "operations", "warehouse"} or (role == "production" and event_type == "production")


def _text(value, label: str, *, required: bool = True, limit: int = 200) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str) or len(value.strip()) > limit or (required and not value.strip()):
        raise ValueError(f"Поле «{label}» должно быть строкой до {limit} символов")
    return value.strip()


def _number(value, unit: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("Количество должно быть числом")
    try:
        number = Decimal(str(value).strip().replace(",", "."))
        quantum = Decimal("0.001") if unit == "кг" else Decimal("1")
        if not number.is_finite() or abs(number) > Decimal("1000000000000") or number.quantize(quantum) != number:
            raise ValueError("Укажите до трёх знаков после запятой для кг и целое число для шт.")
        return number.quantize(quantum)
    except (InvalidOperation, ArithmeticError) as exc:
        raise ValueError("Некорректное количество") from exc


def _decimal(value: Decimal) -> str:
    return format(value.normalize(), "f") if value else "0"


def _key(row: dict) -> tuple[str, str, str, str]:
    return row["sku"], row["lot"], row["warehouse"], row["unit"]


def _hash(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _clean(record: dict) -> dict:
    return {key: value for key, value in record.items() if key not in {"_updatedAt", "requestHash"}}


def get_state(conn, event: dict | None = None) -> dict:
    rows = conn.execute(
        "SELECT id,data,updated,coll FROM crm_records WHERE coll IN (?,?) ORDER BY updated DESC,id",
        (BALANCES, EVENTS),
    ).fetchall()
    data = {"balances": [], "events": []}
    for row in rows:
        if row[3] == BALANCES:
            data["balances"].append(_clean(crm._row_to_rec(row)))
        elif len(data["events"]) < 150:
            data["events"].append(_clean(crm._row_to_rec(row)))
    data["balances"].sort(key=lambda row: (row["warehouse"], row["sku"], row["lot"]))
    if event:
        data["event"] = _clean(event)
    return data


def _normalize(raw: dict) -> dict:
    event_id = _text(raw.get("id"), "ID операции", limit=128)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", event_id):
        raise ValueError("ID операции содержит недопустимые символы")
    kind = _text(raw.get("type"), "Операция")
    if kind not in TYPES:
        raise ValueError("Неизвестная складская операция")
    reference = _text(raw.get("reference"), "Основание", required=False, limit=500)
    order = _text(raw.get("orderId"), "Заказ", required=False)
    reverse_of = _text(raw.get("reverseOf"), "Исходная операция", required=False, limit=128)
    source = raw.get("source")
    if source is not None:
        if not isinstance(source, dict):
            raise ValueError("Укажите документ-основание")
        collection = _text(source.get("collection"), "Тип документа")
        if collection not in SOURCE_TYPES.get(kind, ()):
            raise ValueError("Этот документ нельзя использовать для выбранной операции")
        source = {"collection": collection, "id": _text(source.get("id"), "Документ")}
    if kind in {"reserve", "release"}:
        if source:
            if order and order != source["id"]:
                raise ValueError("Заказ и документ-основание должны совпадать")
            order = source["id"]
        if not order:
            raise ValueError("Для резерва или его снятия укажите заказ")
    if kind not in {"reserve", "release"} and not source and not reference:
        raise ValueError("Выберите документ-основание или укажите основание вручную")
    if kind not in {"reserve", "release", "dispatch", "return"} and order:
        raise ValueError("В этой операции заказ определяется документом-основанием")
    event = {
        "id": event_id, "type": kind, "reference": reference,
        "source": source, "orderId": order or None, "reverseOf": reverse_of or None,
    }
    raw_lines = raw.get("lines", [])
    if not isinstance(raw_lines, list) or len(raw_lines) > 200:
        raise ValueError("В операции может быть не больше 200 строк")
    if kind == "reversal":
        if not reverse_of or raw_lines:
            raise ValueError("Для отмены укажите исходную операцию без новых строк")
        return {**event, "lines": []}
    if reverse_of or not raw_lines:
        raise ValueError("Добавьте хотя бы одну складскую строку")
    parsed = {}
    for line in raw_lines:
        if not isinstance(line, dict):
            raise ValueError("Проверьте формат складской строки")
        sku = _text(line.get("sku"), "SKU")
        lot = _text(line.get("lot"), "Партия")
        wh = _text(line.get("warehouse"), "Склад")
        unit = _text(line.get("unit"), "Единица")
        expected_unit = "кг" if sku in RAW_SKUS else "шт."
        if unit not in ({expected_unit} if sku in RAW_SKUS else {"шт.", "кг"}):
            raise ValueError(f"Для SKU «{sku}» единица учёта — {expected_unit}")
        qty = _number(line.get("qty"), unit)
        if not qty or (kind not in {"adjustment", "production_recipe"} and qty < 0):
            raise ValueError("Укажите положительное количество по каждой строке")
        key = (sku, lot, wh, unit)
        parsed[key] = parsed.get(key, Decimal(0)) + qty
    lines = [
        {"sku": sku, "lot": lot, "warehouse": wh, "unit": unit, "qty": _decimal(_number(qty, unit))}
        for (sku, lot, wh, unit), qty in sorted(parsed.items()) if qty
    ]
    if not lines:
        raise ValueError("Операция не меняет остаток ни по одной партии")
    if raw.get("clearBalance") is True:
        if kind != "adjustment" or len(lines) != 1 or Decimal(lines[0]["qty"]) >= 0:
            raise ValueError("Для удаления укажите одну партию с отрицательным количеством")
        event["clearBalance"] = True
    return {**event, "lines": lines}


def _posting_source(tx, event: dict) -> tuple[dict | None, str | None]:
    source = event["source"]
    if not source:
        return None, None
    coll, rid = source["collection"], source["id"]
    record = logistics.get_doc(tx, rid) if coll == "logistics" else crm.get_record(tx, coll, rid)
    if not record:
        raise ValueError("Документ-основание не найден")
    kind = event["type"]
    if coll == "logistics" and record["kind"] != ("supply" if kind in RECEIPT_TYPES else "dispatch"):
        raise ValueError("Тип документа логистики не подходит для этой операции")
    if coll == "logistics" and kind in {"dispatch", "return"} and record.get("shipmentId"):
        raise ValueError("Проведите складскую операцию по связанной отгрузке CRM.")
    source_order = record.get("orderId") or (rid if coll == "orders" else None)
    if source_order and kind in {"reserve", "release", "dispatch", "return"}:
        if event["orderId"] and event["orderId"] != source_order:
            raise ValueError("Заказ должен совпадать с заказом в документе")
        event["orderId"] = source_order
    unique_source = kind in RECEIPT_TYPES or kind in {"production", "production_recipe", "dispatch"}
    source_kind = "production" if kind == "production_recipe" else kind
    return record, _hash([source_kind, coll, rid]) if unique_source else None


def _document_quantities(doc: dict | None) -> dict:
    """Use registered SKU and package counts where the document provides them."""
    if not doc:
        return {}
    items = doc.get("items") or [doc]
    limits = {}
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict) or not (sku := item.get("sku") or item.get("skuId")) or not isinstance(sku, str):
            continue
        packs = item.get("packs")
        if packs is None and item.get("unit") in (None, "", "шт.", "шт", "штук"):
            packs = item.get("qty")
        previous = limits.get(sku, Decimal(0))
        try:
            limits[sku] = None if previous is None else previous + _number(packs, "шт.")
        except ValueError:
            limits[sku] = None
    return limits


def _check_document_lines(lines: list[dict], limits: dict) -> None:
    if not limits:
        return
    quantities = {}
    for row in lines:
        sku = row["sku"]
        if sku not in limits:
            raise ValueError(f"SKU «{sku}» отсутствует в документе")
        quantities[sku] = quantities.get(sku, Decimal(0)) + Decimal(row["qty"])
    for sku, qty in quantities.items():
        if limits[sku] is not None and qty > limits[sku]:
            raise ValueError(f"Количество SKU «{sku}» превышает указанное в документе")


def receipt_lines(tx, doc: dict, kind: str, *, fallback_warehouse: str = "") -> list[dict]:
    material = RECEIPT_TYPES[kind]
    warehouse = str(doc.get("warehouse") or "").strip() or fallback_warehouse
    lines = []
    for item in doc["items"]:
        if (item.get("material") or "") != material:
            continue
        if not warehouse:
            raise ValueError("Укажите склад назначения поставки.")
        lot = str(item.get("lot") or "").strip()
        if not lot:
            raise ValueError("Укажите номер партии каждой позиции поставки.")
        if material:
            if item.get("qcStatus") != "Пройден" or item.get("unit") not in {"кг", "т"}:
                raise ValueError("Проверьте контроль качества и единицу приёмки сырья.")
            sku = material.upper()
            if material == "paste" and item.get("skuId") == "PASTE":
                from manufacturing import RAW_WAREHOUSE
                if warehouse != RAW_WAREHOUSE or item["unit"] != "кг":
                    raise ValueError("Пасту из каталога принимайте в килограммах на «Склад сырья».")
            unit = "кг"
            qty = Decimal(str(item["qty"])) * (1000 if item["unit"] == "т" else 1)
        else:
            sku = item.get("skuId")
            product = crm.get_record(tx, "skus", sku) if sku and sku not in RAW_SKUS else None
            if not product:
                raise ValueError("Выберите товар из каталога для каждой позиции поставки.")
            stock_type = product.get("stockType")
            if stock_type:
                from manufacturing import RAW_WAREHOUSE, FINISHED_WAREHOUSE
                destination = FINISHED_WAREHOUSE if stock_type == "finished" else RAW_WAREHOUSE
                if warehouse != destination:
                    raise ValueError(f"Для «{product.get('name') or sku}» выберите «{destination}».")
            if stock_type == "raw":
                if item.get("unit") != "кг":
                    raise ValueError("Для сырья укажите массу в килограммах.")
                unit = "кг"
            else:
                if item.get("unit") not in {"шт.", "шт", "штук", "упак", "упак."}:
                    raise ValueError("Для поступления товара укажите количество в штуках или упаковках.")
                unit = "шт."
            qty = item["qty"]
        lines.append({"sku": sku, "lot": lot, "warehouse": warehouse,
                      "unit": unit, "qty": _decimal(_number(qty, unit))})
    return lines


def supply_receipts(tx, doc_id: str) -> dict:
    result = {}
    for kind in RECEIPT_TYPES:
        index = crm.get_record(tx, SOURCE_POSTINGS, _hash([kind, "logistics", doc_id]))
        if index:
            event = crm.get_record(tx, EVENTS, index["eventId"])
            if event:
                result[kind] = event
    return result


def receipt_quantities(lines):
    result = {}
    for row in lines:
        key = _key(row)
        result[key] = result.get(key, Decimal(0)) + Decimal(row["qty"])
    return result


def _validate_event(tx, event: dict, source: dict | None) -> None:
    kind, lines, order_id = event["type"], event["lines"], event["orderId"]
    if kind == "production_recipe":
        return  # Only the manufacturing workflow can submit the derived lines.
    if kind in {"opening", "adjustment"}:
        for row in lines:
            stock_type = (crm.get_record(tx, "skus", row["sku"]) or {}).get("stockType")
            if stock_type and row["unit"] != ("кг" if stock_type == "raw" else "шт."):
                raise ValueError("Единица складского учёта должна совпадать с типом товара.")
    raw = [row for row in lines if row["sku"] in RAW_SKUS]
    finished = [row for row in lines if row["sku"] not in RAW_SKUS]
    if order_id and kind in {"reserve", "dispatch"}:
        order = crm.get_record(tx, "orders", order_id)
        if not order or order.get("status") in CANCELLED:
            raise ValueError("Для операции нужен действующий заказ")
        _check_document_lines(finished, _document_quantities(order))
    if kind == "dispatch" and source:
        if source.get("status") in CANCELLED:
            raise ValueError("Нельзя провести отменённую отгрузку")
        _check_document_lines(finished, _document_quantities(source))
    if kind in {"reserve", "release", "dispatch", "return"} and (raw or any(
        (crm.get_record(tx, "skus", row["sku"]) or {}).get("stockType") in {"raw", "packaging"}
        or row["unit"] != "шт." for row in finished
    )):
        raise ValueError("Резерв, отгрузка и возврат относятся к готовой продукции")
    if kind == "receipt_goods" and not source:
        raise ValueError("Для прихода товара выберите документ поставки.")
    if kind in {"receipt_paste", "receipt_powder"}:
        material = "paste" if kind == "receipt_paste" else "powder"
        if finished or any(row["sku"] != material.upper() for row in raw):
            raise ValueError("Тип сырья в строках должен совпадать с видом приёмки")
    if kind in RECEIPT_TYPES and source:
        if source.get("status") != "Принят":
            raise ValueError("Приёмка возможна после подтверждения документа поставки")
        expected = receipt_lines(tx, source, kind, fallback_warehouse=lines[0]["warehouse"])
        if receipt_quantities(lines) != receipt_quantities(expected):
            raise ValueError("Партии, склад и количество должны совпадать с позициями поставки")
    if kind == "production":
        if not raw or len({row["sku"] for row in raw}) != 1:
            raise ValueError("Для производства укажите расход одного вида сырья")
        rejected = source and source.get("qcStatus") == "Отклонён"
        if (rejected and finished) or (not rejected and not finished):
            raise ValueError("Брак проводится только как расход сырья, успешная партия — с фактическим выпуском")
        if source:
            if (crm.get_record(tx, "skus", str(source.get("sku") or "")) or {}).get("stockType") == "finished":
                raise ValueError("Для готового товара со складской рецептурой сохраните завершённую партию в производстве.")
            if source.get("status") != "Завершено" or source.get("qcStatus") not in {"Пройден", "Отклонён"}:
                raise ValueError("Для проведения завершите производственную партию и подтвердите результат контроля")
            raw_sku = raw[0]["sku"]
            supply = logistics.get_doc(tx, source["supplyId"]) if source.get("supplyId") else None
            if supply and not any(item.get("material") == raw_sku.lower()
                                  and item.get("lot") == source.get("inputLot")
                                  and item.get("qcStatus") == "Пройден"
                                  for item in supply.get("items", [])):
                raise ValueError("В поставке нет принятой партии выбранного вида сырья")
            usage_field = "pasteUsedKg" if raw_sku == "PASTE" else "powderUsedKg"
            if any(row["lot"] != source.get("inputLot") for row in raw) or (
                sum(Decimal(row["qty"]) for row in raw) != _number(source.get(usage_field), "кг")
            ):
                raise ValueError("Входящая партия и расход сырья должны совпадать с производственным документом")
            if not rejected and (
                any(row["lot"] != source.get("lot") or row["sku"] != source.get("sku") for row in finished)
                or sum(Decimal(row["qty"]) for row in finished) != _number(source.get("actualQty"), "шт.")
            ):
                raise ValueError("SKU, партия и выпуск должны совпадать с производственным документом")


def _effect(event: dict, row: dict, balance: dict | None) -> dict:
    kind, order = event["type"], event["orderId"]
    qty = Decimal(row["qty"])
    stock, reserve = qty, Decimal(0)
    if kind in {"reserve", "release"}:
        stock, reserve = Decimal(0), qty if kind == "reserve" else -qty
    elif kind == "production" and row["sku"] in RAW_SKUS:
        stock = -qty
    elif kind == "dispatch":
        stock = -qty
        held = Decimal((balance or {}).get("reservations", {}).get(order, "0"))
        reserve = -min(held, qty)
    shipped = qty if order and kind == "dispatch" else -qty if order and kind == "return" else Decimal(0)
    return {
        **row, "stockChange": _decimal(stock), "reservedChange": _decimal(reserve),
        "shippedChange": _decimal(shipped), "orderId": order,
    }


def _apply_effect(tx, row: dict, balance: dict | None) -> None:
    sku, lot, wh, unit = _key(row)
    qty = Decimal((balance or {}).get("onHand", "0")) + Decimal(row["stockChange"])
    reservations = dict((balance or {}).get("reservations", {}))
    if row["reservedChange"] != "0":
        order = row["orderId"]
        held = Decimal(reservations.get(order, "0")) + Decimal(row["reservedChange"])
        if held < 0:
            raise InventoryConflict(f"Заказ «{order}» не имеет нужного резерва для партии «{lot}»")
        if held:
            reservations[order] = _decimal(held)
        else:
            reservations.pop(order, None)
    reserved = sum((Decimal(value) for value in reservations.values()), Decimal(0))
    available = qty - reserved
    if available < 0 or reserved < 0:
        raise InventoryConflict(f"Недостаточно свободного остатка SKU «{sku}», партия «{lot}», склад «{wh}»")
    _number(qty, unit)
    if not balance and sku not in RAW_SKUS and not crm.get_record(tx, "skus", sku):
        raise ValueError(f"SKU «{sku}» отсутствует в справочнике товаров")
    rid = _hash(_key(row))
    crm._write(tx, BALANCES, {
        "id": rid, "sku": sku, "lot": lot, "warehouse": wh, "unit": unit,
        "onHand": _decimal(qty), "reserved": _decimal(reserved),
        "available": _decimal(available), "reservations": reservations,
    }, rid)


def _apply_order_effect(tx, row: dict, *, enforce_limit: bool) -> None:
    order_id, sku = row["orderId"], row["sku"]
    reserved_delta = Decimal(row["reservedChange"])
    shipped_delta = Decimal(row["shippedChange"])
    if not order_id or not (reserved_delta or shipped_delta):
        return
    rid = _hash([order_id, sku])
    current = crm.get_record(tx, ORDER_STOCK, rid) or {}
    reserved = Decimal(current.get("reserved", "0")) + reserved_delta
    shipped = Decimal(current.get("shipped", "0")) + shipped_delta
    if reserved < 0 or shipped < 0:
        raise InventoryConflict(f"Операция превышает проведённое количество SKU «{sku}» по заказу")
    if enforce_limit:
        order = crm.get_record(tx, "orders", order_id)
        limit = _document_quantities(order).get(sku)
        if limit is not None and reserved + shipped > limit:
            raise InventoryConflict(f"Резерв и отгрузка SKU «{sku}» превышают количество в заказе")
    crm._write(tx, ORDER_STOCK, {
        "id": rid, "orderId": order_id, "sku": sku,
        "reserved": _decimal(reserved), "shipped": _decimal(shipped),
    }, rid)


def post_event(conn, payload: dict, *, actor: str, role: str) -> dict:
    event = _normalize(payload)
    if not may_post(role, event["type"]):
        raise PermissionError("Нет прав проводить эту складскую операцию")
    with crm.write_transaction(conn) as tx:
        return get_state(tx, _post_event(tx, event, actor=actor))


def post_supply_receipt(tx, doc, kind, lines, *, actor):
    event = _normalize({
        "id": str(uuid4()), "type": kind, "lines": lines,
        "source": {"collection": "logistics", "id": doc["id"]},
        "reference": "Автоматическая приёмка " + doc["number"][:450],
    })
    return _post_event(tx, event, actor=actor)


def _post_event(tx, event, *, actor):
    req_hash = _hash(event)
    posted = crm.get_record(tx, EVENTS, event["id"])
    if posted:
        if posted.get("requestHash") != req_hash:
            raise InventoryConflict("ID уже используется для другой складской операции")
        return posted

    original = None
    source_key = None
    if event["type"] == "reversal":
        original = crm.get_record(tx, EVENTS, event["reverseOf"])
        if not original or original["type"] == "reversal":
            raise ValueError("Исходная складская операция не найдена или уже является отменой")
        if original.get("reversedBy"):
            raise InventoryConflict("Эта операция уже отменена")
        prepared = [
            {**effect,
             "stockChange": _decimal(-Decimal(effect["stockChange"])),
             "reservedChange": _decimal(-Decimal(effect["reservedChange"])),
             "shippedChange": _decimal(-Decimal(effect.get("shippedChange", "0")))}
            for effect in original["lines"]
        ]
    else:
        record, source_key = _posting_source(tx, event)
        indexed = source_key and crm.get_record(tx, SOURCE_POSTINGS, source_key)
        if indexed:
            previous = crm.get_record(tx, EVENTS, indexed["eventId"])
            if previous and not previous.get("reversedBy"):
                raise InventoryConflict("Этот документ уже проведён на складе")
        _validate_event(tx, event, record)
        if record:
            event["sourceSnapshot"] = {
                key: record[key] for key in ("number", "date", "status") if record.get(key)
            }
        prepared = event["lines"]

    effects = []
    for row in prepared:
        balance = crm.get_record(tx, BALANCES, _hash(_key(row)))
        if event.get("clearBalance"):
            if Decimal((balance or {}).get("onHand", "0")) != -Decimal(row["qty"]):
                raise InventoryConflict("Остаток изменился. Обновите склад и выберите партию снова.")
            if Decimal(balance.get("reserved", "0")):
                raise InventoryConflict("Сначала снимите резерв по этой партии.")
        if event["type"] == "opening" and balance:
            raise InventoryConflict("Начальный остаток для этой партии уже задан. Используйте корректировку.")
        effect = row if original else _effect(event, row, balance)
        _apply_effect(tx, effect, balance)
        _apply_order_effect(tx, effect, enforce_limit=event["type"] in {"reserve", "dispatch"})
        effects.append(effect)

    event.update({"lines": effects, "createdAt": crm._now(), "createdBy": actor, "requestHash": req_hash})
    event = crm._write(tx, EVENTS, event, event["id"])
    if original:
        original["reversedBy"] = event["id"]
        crm._write(tx, EVENTS, {k: v for k, v in original.items() if k != "_updatedAt"}, original["id"])
        if original["type"] == "production_recipe":
            batch_id = original["source"]["id"]
            batch = crm.get_record(tx, "production", batch_id)
            if batch and batch.get("stockEventId") == original["id"]:
                crm._write(tx, "production", crm._record_data({**batch, "stockReversed": True}, batch_id), batch_id)
    if source_key:
        crm._write(tx, SOURCE_POSTINGS, {"id": source_key, "eventId": event["id"]}, source_key)
    return event

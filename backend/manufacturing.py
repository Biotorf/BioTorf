"""Catalog recipes and atomic posting of completed manufacturing batches."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import uuid4

import crm
import inventory

RAW_WAREHOUSE = "Склад сырья"
FINISHED_WAREHOUSE = "Склад готовой продукции"


def sku(conn, key):
    if key == "PASTE":
        return {"id": key, "name": "Паста-концентрат", "stockType": "raw"}
    return crm.get_record(conn, "skus", key) or {}


def number(value, label):
    try:
        amount = Decimal(str(value).replace(",", "."))
        if amount.is_finite() and 0 < amount <= 10**12:
            return amount
    except (InvalidOperation, ValueError):
        pass
    raise ValueError(f"Укажите положительное значение: {label}.")


def normalize_catalog(tx, record, current):
    kind = record.get("stockType") or ""
    if kind not in {"", "raw", "packaging", "finished"}:
        raise ValueError("Выберите тип складского товара.")
    if record["id"] in inventory.RAW_SKUS:
        raise ValueError("Этот артикул зарезервирован для системного сырья.")
    if current and (current.get("stockType") or "finished") != (kind or "finished"):
        if any(row["sku"] == record["id"] for row in crm.list_records(tx, inventory.BALANCES)):
            raise ValueError("Тип товара со складской историей менять нельзя. Создайте новый артикул.")
    if kind != "finished" or "components" not in record:
        return record
    rows = record["components"]
    if not isinstance(rows, list) or len(rows) > 50:
        raise ValueError("У рецептуры может быть до 50 компонентов.")
    result = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("sku"), str):
            raise ValueError("Выберите компонент из каталога.")
        key = row["sku"]
        component = sku(tx, key)
        if key == record["id"] or key in seen or component.get("stockType") not in {"raw", "packaging"}:
            raise ValueError("Каждый компонент рецептуры должен быть сырьём или упаковкой и встречаться один раз.")
        seen.add(key)
        qty = number(row.get("qty"), "расход на одну упаковку")
        inventory._number(qty, "кг" if component["stockType"] == "raw" else "шт.")
        result.append({"sku": key, "qty": inventory._decimal(qty)})
    return {**record, "components": result}


def active_posting(tx, batch_id):
    index = crm.get_record(tx, inventory.SOURCE_POSTINGS,
                           inventory._hash(["production", "production", batch_id]))
    event = index and crm.get_record(tx, inventory.EVENTS, index["eventId"])
    return event if event and not event.get("reversedBy") else None


def finish(tx, current, batch, actor):
    batch = {key: value for key, value in batch.items() if key not in {"stockEventId", "stockReversed"}}
    posted = active_posting(tx, batch["id"])
    if posted and posted["type"] == "production_recipe":
        changing = any(batch.get(key) != (current or {}).get(key)
                       for key in ("sku", "status", "qcStatus", "lot", "actualQty", "pasteUsedKg", "inputLot", "recipeVersion"))
        if changing:
            raise ValueError("Для изменения проведённого выпуска сначала сделайте сторно в журнале.")
        return {**batch, "stockEventId": posted["id"]}
    product = sku(tx, str(batch.get("sku") or ""))
    if product.get("stockType") in {"raw", "packaging"}:
        raise ValueError("В производство выберите готовый товар из каталога.")
    if product.get("stockType") != "finished" or batch.get("status") != "Завершено":
        return batch
    if posted:
        return batch
    if current and current.get("stockEventId") and current.get("status") == "Завершено":
        raise ValueError("Выпуск сторнирован. Сначала верните партию в работу.")
    recipe = product.get("components") or []
    if not recipe or not product.get("recipeVersion"):
        raise ValueError("В каталоге заполните версию рецептуры и список компонентов готового товара.")
    if batch.get("qcStatus") not in {"Пройден", "Отклонён"}:
        raise ValueError("Укажите результат контроля качества.")
    lot = str(batch.get("lot") or "").strip()
    if not lot:
        raise ValueError("Укажите номер готовой партии.")
    count = inventory._number(number(batch.get("actualQty"), "фактический выпуск"), "шт.")
    balances = sorted(crm.list_records(tx, inventory.BALANCES), key=lambda row: (row["lot"], row["sku"]))
    components = []
    for item in recipe:
        component = sku(tx, item["sku"])
        if component.get("stockType") not in {"raw", "packaging"}:
            raise ValueError(f"Компонент {item['sku']} отсутствует в каталоге сырья и упаковки.")
        unit = "кг" if component["stockType"] == "raw" else "шт."
        need = number(item["qty"], "расход на одну упаковку") * count
        if item["sku"] == "PASTE" and batch.get("pasteUsedKg") not in (None, ""):
            need = number(batch["pasteUsedKg"], "фактический расход пасты")
        if unit == "кг":
            need = need.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        if need <= 0:
            raise ValueError("Расход компонента слишком мал для точности складского учёта.")
        candidates = [row for row in balances if row["sku"] == item["sku"] and row["unit"] == unit
                      and row["warehouse"] == RAW_WAREHOUSE and Decimal(row["available"]) > 0
                      and (item["sku"] != "PASTE" or not batch.get("inputLot") or row["lot"] == batch["inputLot"])]
        for row in candidates:
            take = min(need, Decimal(row["available"]))
            components.append({"sku": item["sku"], "lot": row["lot"], "warehouse": RAW_WAREHOUSE,
                               "unit": unit, "qty": inventory._decimal(-take)})
            need -= take
            if not need:
                break
        if need:
            raise ValueError(f"На складе сырья не хватает «{component['name']}»: {inventory._decimal(need)} {unit}")
    lines = list(components)
    if batch["qcStatus"] == "Пройден":
        lines.append({"sku": product["id"], "lot": lot, "warehouse": FINISHED_WAREHOUSE,
                      "unit": "шт.", "qty": inventory._decimal(count)})
    event = inventory._normalize({
        "id": str(uuid4()), "type": "production_recipe",
        "source": {"collection": "production", "id": batch["id"]}, "lines": lines,
    })
    # Source validation in the ledger reads the batch from the same transaction.
    saved = {**batch, "stockEventId": event["id"], "recipeVersion": product["recipeVersion"]}
    crm._write(tx, "production", saved, batch["id"])
    inventory._post_event(tx, event, actor=actor)
    return saved

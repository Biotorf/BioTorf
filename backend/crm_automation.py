"""CRM workflow automations that run in the source record's transaction."""

import hashlib
from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import uuid4

import crm

RULE_ID = "invoice_payment"
RULE_TITLE = "Контроль оплаты счёта"
RULE_DESCRIPTION = (
    "Создаёт задачу по новому неоплаченному счёту. Использует срок из счёта, если он указан, "
    "и закрывает задачу при подтверждении оплаты или отмене счёта. "
    "Отключение останавливает создание новых задач."
)
_CONFIG = "automationRules"
_ACTIVITY = "automationActivity"
_FINAL_TASK = {"Выполнена", "Отменена", "Отменено"}
_VOID_INVOICE = {"отменен", "отменён", "аннулирован", "отклонен", "отклонён"}


def _record_activity(tx, action: str, *, actor: str, invoice_id: str | None = None,
                     task_id: str | None = None, reason: str | None = None) -> None:
    activity_id = uuid4().hex
    crm._write(tx, _ACTIVITY, {
        "id": activity_id, "ruleId": RULE_ID, "action": action, "at": crm._now(),
        "actor": actor, "recordId": invoice_id, "taskId": task_id, "reason": reason,
    }, activity_id)


def state(conn, can_manage: bool) -> dict:
    setting = crm.get_record(conn, _CONFIG, RULE_ID) or {}
    rows = conn.execute(
        "SELECT id,data,updated FROM crm_records WHERE coll=? ORDER BY updated DESC,id DESC LIMIT 30",
        (_ACTIVITY,),
    )
    return {
        "rules": [{
            "id": RULE_ID, "title": RULE_TITLE, "description": RULE_DESCRIPTION,
            "enabled": setting.get("enabled", True), "updatedAt": setting.get("_updatedAt"),
            "updatedBy": setting.get("updatedBy"),
        }],
        "activity": [crm._record_data(crm._row_to_rec(row), row[0]) for row in rows],
        "canManage": can_manage,
    }


def configure(conn, rule_id: str, enabled: bool, actor: str) -> bool:
    if rule_id != RULE_ID:
        return False
    with crm.write_transaction(conn) as tx:
        before = crm.get_record(tx, _CONFIG, RULE_ID) or {}
        if before.get("enabled", True) != enabled:
            crm._write(tx, _CONFIG, {"id": RULE_ID, "enabled": enabled, "updatedBy": actor}, RULE_ID)
            _record_activity(tx, "enabled" if enabled else "disabled", actor=actor)
    return True


def _task_id(invoice_id: str) -> str:
    digest = hashlib.sha256(invoice_id.encode()).hexdigest()[:32]
    return "T-AUTO-" + digest


def _closed_action(invoice: dict | None) -> tuple[str, str] | None:
    if invoice is None:
        return "canceled", "invoice_deleted"
    status = str(invoice.get("status") or "").strip().casefold()
    if status in _VOID_INVOICE:
        return "canceled", "invoice_canceled"
    paid = invoice.get("paid")
    if paid is True or str(paid).strip().casefold() in {"true", "1", "да"} or status == "оплачен":
        return "completed", "payment_confirmed"
    return None


def _has_payable_amount(invoice: dict) -> bool:
    try:
        amount = Decimal(str(invoice.get("amount", "")).strip().replace(",", "."))
        return amount.is_finite() and amount > 0
    except InvalidOperation:
        return False


def _due(invoice: dict) -> str | None:
    try:
        return date.fromisoformat(str(invoice.get("due") or "").strip()).isoformat()
    except ValueError:
        return None


def _owner(tx, invoice: dict, actor: str) -> str:
    owner = str(invoice.get("owner") or "").strip()
    if owner:
        return owner
    for coll, key in (("journeys", "journeyId"), ("orders", "orderId"), ("farms", "farmId")):
        record_id = invoice.get(key)
        if isinstance(record_id, str) and record_id:
            parent = crm.get_record(tx, coll, record_id) or {}
            owner = str(parent.get("owner") or "").strip()
            if owner:
                return owner
    return actor


def invoice_changed(tx, invoice_id: str, before: dict | None, after: dict | None,
                    *, actor: str, allow_new: bool = True) -> None:
    task_id = _task_id(invoice_id)
    task = crm.get_record(tx, "tasks", task_id)
    if task and (task.get("_automationRule") != RULE_ID or task.get("refId") != invoice_id):
        return  # Do not overwrite a manually supplied task with the same ID.
    closed = _closed_action(after)
    if task:
        if task.get("status") in _FINAL_TASK:
            return
        if closed:
            action, reason = closed
            next_task = {**task, "status": "Выполнена" if action == "completed" else "Отменена"}
            crm._write(tx, "tasks", crm._record_data(next_task, task_id), task_id)
            _record_activity(tx, action, actor=actor, invoice_id=invoice_id, task_id=task_id, reason=reason)
        elif before and _due(before) != _due(after) and task.get("due") == _due(before):
            crm._write(tx, "tasks", crm._record_data({**task, "due": _due(after)}, task_id), task_id)
            _record_activity(tx, "rescheduled", actor=actor, invoice_id=invoice_id, task_id=task_id)
        return

    if before is not None or closed or not allow_new or not _has_payable_amount(after):
        return
    setting = crm.get_record(tx, _CONFIG, RULE_ID) or {}
    if not setting.get("enabled", True) or crm.get_record(tx, crm._DELETED_PREFIX + "tasks", task_id):
        return
    number = str(after.get("number") or invoice_id).strip()
    crm._write(tx, "tasks", {
        "id": task_id, "title": f"Проверить оплату по счёту {number}",
        "owner": _owner(tx, after, actor), "due": _due(after), "priority": "Средний",
        "status": "Открыта", "createdAt": crm._now(), "refKind": "invoice", "refId": invoice_id,
        "farmId": after.get("farmId"), "_automationRule": RULE_ID,
    }, task_id)
    _record_activity(tx, "created", actor=actor, invoice_id=invoice_id, task_id=task_id)

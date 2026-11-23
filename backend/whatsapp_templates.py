"""Approved WhatsApp template configuration and signed delivery status storage."""

import json
import re
from contextlib import closing

import db

# A delayed "sent" or "failed" event cannot override proof of delivery/read.
STATUSES = {
    "sent": (1, "Передано WhatsApp"),
    "failed": (2, "Ошибка доставки"),
    "delivered": (3, "Доставлено"),
    "read": (4, "Прочитано"),
}


def approved_templates(raw: str) -> list[dict]:
    values = json.loads(raw or "[]")
    if not isinstance(values, list):
        raise ValueError("WHATSAPP_TEMPLATES_JSON должен содержать список шаблонов")
    templates = []
    seen = set()
    for value in values:
        if not isinstance(value, dict):
            raise ValueError("Каждый шаблон WhatsApp должен быть объектом")
        name, language = value.get("name"), value.get("language")
        label = value.get("label")
        parameters = value.get("parameters", [])
        if not (isinstance(name, str) and re.fullmatch(r"[a-z0-9_]{1,512}", name) and
                isinstance(language, str) and re.fullmatch(r"[a-z]{2,3}(?:_[A-Z]{2,3})?", language) and
                isinstance(label, str) and 1 <= len(label.strip()) <= 120 and
                isinstance(parameters, list) and len(parameters) <= 30 and
                all(isinstance(p, str) and 1 <= len(p.strip()) <= 120 for p in parameters)):
            raise ValueError("Проверьте name, language, label и parameters шаблона WhatsApp")
        if (name, language) in seen:
            raise ValueError("Имя и язык шаблона WhatsApp повторяются")
        seen.add((name, language))
        templates.append({"name": name, "language": language, "label": label.strip(),
                          "parameters": [p.strip() for p in parameters]})
    return templates


def record_status(event: dict) -> bool:
    provider_id = event.get("id")
    code = event.get("status")
    if not isinstance(provider_id, str) or not 1 <= len(provider_id) <= 512:
        return False
    if not isinstance(code, str) or code not in STATUSES:
        return False
    rank, _ = STATUSES[code]
    errors = event.get("errors")
    first_error = errors[0] if isinstance(errors, list) and errors else None
    error = (first_error.get("title") or first_error.get("message")) if isinstance(first_error, dict) else None
    with closing(db.connect()) as conn:
        conn.execute(
            """
INSERT INTO whatsapp_receipts (provider_id, code, rank, error) VALUES (?,?,?,?)
ON CONFLICT(provider_id) DO UPDATE SET code=excluded.code, rank=excluded.rank, error=excluded.error
WHERE whatsapp_receipts.rank < excluded.rank
""",
            (provider_id, code, rank, str(error)[:200] if error else None),
        )
        conn.commit()
    # Store the event even if Meta called back before the outgoing entry existed.
    apply_status(provider_id)
    return True


def apply_status(provider_id: str) -> None:
    with closing(db.connect()) as conn:
        receipt = conn.execute(
            "SELECT code, rank, error FROM whatsapp_receipts WHERE provider_id=?",
            (provider_id,),
        ).fetchone()
        if not receipt:
            return
        rows = conn.execute(
            "SELECT id, payload FROM comms WHERE kind='whatsapp' AND dir='out' AND external_id=?",
            (provider_id,),
        ).fetchall()
        if not rows:
            # Rows saved prior to delivery tracking only carry the ID in their payload.
            rows = conn.execute(
                "SELECT id, payload FROM comms WHERE kind='whatsapp' AND dir='out' "
                "AND external_id IS NULL AND payload LIKE ?",
                (f'%{provider_id}%',),
            ).fetchall()
        _, label = STATUSES[receipt["code"]]
        protected = [text for rank, text in STATUSES.values() if rank > receipt["rank"]]
        guard = "AND (status IS NULL OR status NOT IN (" + ",".join("?" for _ in protected) + "))" if protected else ""
        for row in rows:
            payload = json.loads(row["payload"] or "{}")
            if payload.get("waMessageId") != provider_id:
                continue
            payload["waReceipt"] = receipt["code"]
            if receipt["code"] == "failed":
                payload["sendError"] = receipt["error"] or "WhatsApp не доставил сообщение"
            else:
                payload.pop("sendError", None)
            conn.execute(
                f"UPDATE comms SET status=?, payload=? WHERE id=? {guard}",
                (label, json.dumps(payload, ensure_ascii=False), row["id"], *protected),
            )
        conn.commit()

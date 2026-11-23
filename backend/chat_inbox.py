"""Common inbox state shared by CRM employees."""

from datetime import datetime, timezone
import re
from uuid import uuid4

import auth
import crm
import db as store
import users

MANAGERS = {"director", "operations", "sales_head", "dispatcher"}


class InboxError(Exception):
    def __init__(self, status: int, detail: str | dict):
        self.status = status
        self.detail = detail
        super().__init__(detail)


def assignees(login: str, role: str) -> list[dict]:
    staff = users.list_all()
    if not staff and auth.can_write(role, "comms"):
        return [{"login": login, "name": "Текущий сотрудник"}]
    return [
        {"login": row["login"], "name": row["name"]}
        for row in staff if row["active"] and auth.can_write(row["role"], "comms")
        and (role in MANAGERS or row["login"] == login)
    ]


def check_access(current: dict, login: str, role: str, revision: str | None) -> None:
    if not auth.can_write(role, "comms"):
        raise InboxError(403, "Роль не позволяет вести диалоги")
    if current["assignee"] not in (None, login) and role not in MANAGERS:
        raise InboxError(403, "Диалог уже закреплён за другим сотрудником")
    if current["revision"] != revision:
        raise InboxError(409, "Диалог обновил коллега. Откройте актуальные данные и повторите действие")


def write(tx, peer_key: str, values: dict) -> dict:
    revision = uuid4().hex
    tx.execute(
        "INSERT INTO comms_work (peer_key, assignee, state, response_due, lead_id, revision) "
        "VALUES (?,?,?,?,?,?) ON CONFLICT(peer_key) DO UPDATE SET "
        "assignee=excluded.assignee, state=excluded.state, response_due=excluded.response_due, "
        "lead_id=excluded.lead_id, revision=excluded.revision",
        (peer_key, values["assignee"], values["state"], values["responseDue"], values["leadId"], revision),
    )
    return {**values, "revision": revision}


def _check_client_access(role: str) -> None:
    if not auth.can_write_crm_collection(role, "farms"):
        raise InboxError(403, "Роль не позволяет создавать и привязывать клиентов")


def _peer_identity(tx, peer_key: str) -> dict:
    row = tx.execute(
        "SELECT * FROM comms WHERE peer_key=? "
        "ORDER BY CASE WHEN dir='in' THEN 0 ELSE 1 END, ts DESC, id DESC LIMIT 1",
        (peer_key,),
    ).fetchone()
    if not row:
        raise InboxError(404, "Диалог не найден")
    message = store.to_dict(row)
    phone = message.get("phone") or ""
    handle = message.get("handle") or ""
    kind = message["kind"]
    return {
        "name": message.get("contact") or handle or phone,
        "contactName": message.get("contact") or "",
        "phone": phone,
        "telegram": handle if kind == "telegram" else "",
        "source": {"call": "Телефон", "telegram": "Telegram", "whatsapp": "WhatsApp"}.get(kind, kind),
    }


def _phone_identity(value: str) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _matching_clients(tx, identity: dict, extra_phone: str = "") -> list[dict]:
    phones = {_phone_identity(phone) for phone in (identity["phone"], extra_phone)}
    phones = {phone for phone in phones if len(phone) >= 7}
    telegram = identity["telegram"].strip().lstrip("@").casefold()
    if not phones and not telegram:
        return []

    def matches(record):
        return (
            _phone_identity(record.get("phone")) in phones or
            _phone_identity(record.get("whatsapp")) in phones or
            bool(telegram and str(record.get("telegram") or "").strip().lstrip("@").casefold() == telegram)
        )

    contact_clients = {row.get("farmId") for row in crm.list_records(tx, "contacts") if matches(row)}
    return [
        {"id": row["id"], "name": row.get("name") or row["id"]}
        for row in crm.list_records(tx, "farms")
        if row["id"] in contact_clients or matches(row)
    ]


def _current_links(tx, peer_key: str, work: dict):
    existing = store.linked_client(tx, peer_key)
    if existing:
        return existing, crm.get_record(tx, "leads", work["leadId"]) if work["leadId"] else None, []
    lead = crm.get_record(tx, "leads", work["leadId"]) if work["leadId"] else None
    journeys = [
        row for row in crm.list_records(tx, "journeys") if row.get("leadId") == lead["id"]
    ] if lead else []
    links = {
        str(row["farm_id"]) for row in tx.execute(
            "SELECT DISTINCT c.farm_id FROM comms c JOIN crm_records f ON f.coll='farms' AND f.id=c.farm_id "
            "WHERE c.peer_key=?", (peer_key,),
        ).fetchall()
    }
    links.update(record["farmId"] for record in [lead, *journeys] if record and record.get("farmId"))
    if len(links) > 1:
        raise InboxError(409, "В диалоге и сделке указаны разные клиенты. Сначала проверьте существующие связи")
    return next(iter(links), None), lead, journeys


def client_context(peer_key: str, login: str, role: str) -> dict:
    _check_client_access(role)
    with store.connect() as conn:
        work = store.chat_work(conn, peer_key)
        check_access(work, login, role, work["revision"])
        identity = _peer_identity(conn, peer_key)
        linked, _, _ = _current_links(conn, peer_key, work)
        client = crm.get_record(conn, "farms", linked) if linked else None
        linked_client = {"id": client["id"], "name": client.get("name") or client["id"]} if client else None
        return {**identity, "linkedClient": linked_client, "matches": _matching_clients(conn, identity), "revision": work["revision"]}


def save_client(peer_key: str, body: dict, login: str, role: str) -> dict:
    _check_client_access(role)
    available_assignees = {row["login"]: row["name"] for row in assignees(login, role)}
    with store.connect() as conn, crm.write_transaction(conn) as tx:
        store.lock_client_peer(tx, peer_key)
        work = store.chat_work(tx, peer_key, lock=True)
        check_access(work, login, role, work["revision"])
        identity = _peer_identity(tx, peer_key)
        linked, lead, journeys = _current_links(tx, peer_key, work)
        requested = body.get("clientId")
        persisted = store.linked_client(tx, peer_key)
        if persisted:
            # Repeating a committed request (for example after a timeout) is safe.
            if requested and requested != persisted:
                raise InboxError(409, "Диалог уже связан с другим клиентом")
            return {"client": crm.get_record(tx, "farms", persisted), "work": work, "created": False}
        check_access(work, login, role, body["revision"])
        if linked and requested != linked:
            raise InboxError(409, "У диалога уже есть связанный клиент. Выберите его в списке")
        if lead and not auth.can_write_crm_collection(role, "leads"):
            raise InboxError(403, "Роль не позволяет обновлять связанный лид")
        assignee = body.get("assignee") or work["assignee"] or login
        if assignee not in (work["assignee"], login) and assignee not in available_assignees:
            raise InboxError(422, "Выберите доступного сотрудника")
        employee = tx.execute("SELECT name FROM users WHERE login=?", (assignee,)).fetchone()
        owner = employee["name"] if employee else assignee
        if requested:
            client = crm.get_record(tx, "farms", requested)
            if not client:
                raise InboxError(404, "Клиент не найден")
        else:
            name = body["name"].strip()
            phone = body["phone"].strip()
            if not name:
                raise InboxError(422, "Укажите имя или название клиента")
            matches = _matching_clients(tx, identity, phone)
            if matches:
                raise InboxError(409, {
                    "message": "Клиент с таким телефоном или Telegram уже есть. Выберите существующую карточку",
                    "matches": matches,
                })
            client_id = f"F-{uuid4().hex[:12]}"
            client = crm._write(tx, "farms", {
                "id": client_id, "name": name, "type": body["type"].strip(), "phone": phone,
                "region": body.get("region", "").strip(),
                "telegram": identity["telegram"], "source": identity["source"],
                "status": "Активный", "owner": owner,
            }, client_id)
            contact_name = body["contactName"].strip()
            if contact_name or phone or identity["telegram"]:
                contact_id = f"CT-{uuid4().hex[:12]}"
                crm._write(tx, "contacts", {
                    "id": contact_id, "farmId": client_id, "name": contact_name or name,
                    "phone": phone, "telegram": identity["telegram"], "primary": True,
                }, contact_id)
        farm_id = client["id"]
        tx.execute(
            "INSERT INTO comms_client_links (peer_key, farm_id) VALUES (?,?) "
            "ON CONFLICT(peer_key) DO UPDATE SET farm_id=excluded.farm_id",
            (peer_key, farm_id),
        )
        tx.execute("UPDATE comms SET farm_id=? WHERE peer_key=?", (farm_id, peer_key))
        if lead and lead.get("farmId") != farm_id:
            crm._write(tx, "leads", crm._record_data({**lead, "farmId": farm_id}, lead["id"]), lead["id"])
        for journey in journeys:
            if not journey.get("farmId"):
                crm._write(tx, "journeys", crm._record_data({**journey, "farmId": farm_id}, journey["id"]), journey["id"])
        updated = write(tx, peer_key, {
            **work, "assignee": assignee, "state": "working" if work["state"] == "new" else work["state"],
        })
        return {"client": client, "work": updated, "created": not requested}


def update(peer_key: str, body: dict, login: str, role: str) -> dict:
    valid_assignees = {row["login"] for row in assignees(login, role)}
    with store.connect() as conn, crm.write_transaction(conn) as tx:
        if not tx.execute("SELECT 1 FROM comms WHERE peer_key=? LIMIT 1", (peer_key,)).fetchone():
            raise InboxError(404, "Диалог не найден")
        current = store.chat_work(tx, peer_key, lock=True)
        check_access(current, login, role, body["revision"])
        assignee = body["assignee"]
        if assignee and assignee != current["assignee"] and assignee not in valid_assignees:
            raise InboxError(422, "Выберите доступного сотрудника для диалога")
        if assignee and assignee != current["assignee"] and role not in MANAGERS and assignee != login:
            raise InboxError(403, "Можно назначить диалог только себе")
        lead_id = body["leadId"]
        if lead_id != current["leadId"]:
            if not auth.can_write_crm_collection(role, "leads"):
                raise InboxError(403, "Роль не позволяет связывать лиды")
            if lead_id:
                lead = crm.get_record(tx, "leads", lead_id)
                if not lead:
                    raise InboxError(404, "Лид не найден")
                linked = store.linked_client(tx, peer_key)
                if linked and lead.get("farmId") not in (None, "", linked):
                    raise InboxError(409, "Лид уже связан с другим клиентом")
                if linked and not lead.get("farmId"):
                    crm._write(tx, "leads", crm._record_data({**lead, "farmId": linked}, lead_id), lead_id)
        due = body["responseDue"]
        return write(tx, peer_key, {
            "assignee": assignee, "state": body["state"],
            "responseDue": due.astimezone(timezone.utc).isoformat() if due else None,
            "leadId": lead_id,
        })


def create_lead(peer_key: str, revision: str | None, login: str, role: str) -> dict:
    if not auth.can_write_crm_collection(role, "leads"):
        raise InboxError(403, "Роль не позволяет создавать лиды")
    with store.connect() as conn, crm.write_transaction(conn) as tx:
        current = store.chat_work(tx, peer_key, lock=True)
        if current["leadId"]:
            # A repeated button submission returns the same lead.
            check_access(current, login, role, current["revision"])
            lead = crm.get_record(tx, "leads", current["leadId"])
            if lead:
                return {"lead": lead, "work": current}
            raise InboxError(409, "Связанный лид удалён. Снимите привязку перед созданием нового лида")
        check_access(current, login, role, revision)
        row = tx.execute(
            "SELECT * FROM comms WHERE peer_key=? AND dir='in' ORDER BY ts DESC LIMIT 1",
            (peer_key,),
        ).fetchone()
        if not row:
            raise InboxError(422, "Для создания лида требуется входящее обращение")
        message = store.to_dict(row)
        name = message["contact"] or message["handle"] or message["phone"] or "Входящее обращение"
        employee = tx.execute("SELECT name FROM users WHERE login=?", (current["assignee"] or login,)).fetchone()
        lead_id = f"L-{uuid4().hex[:12]}"
        lead = {
            "id": lead_id, "name": name, "contactName": message["contact"] or name,
            "phone": message["phone"] or "", "telegram": message["handle"] if message["kind"] == "telegram" else "",
            "farmId": message["farmId"] or "", "owner": employee["name"] if employee else login,
            "status": "Новый лид", "source": {
                "call": "Телефон", "telegram": "Telegram", "whatsapp": "WhatsApp",
            }.get(message["kind"], message["kind"]),
            "notes": message["text"] or message["note"] or "", "commsPeerKey": peer_key,
            "date": datetime.now(timezone.utc).date().isoformat(),
        }
        # The lead and its inbox link commit together.
        saved = crm._write(tx, "leads", lead, lead_id)
        work = write(tx, peer_key, {
            **current, "leadId": lead_id, "assignee": current["assignee"] or login,
            "state": "working" if current["state"] == "new" else current["state"],
        })
        return {"lead": saved, "work": work}

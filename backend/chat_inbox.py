"""Common inbox state shared by CRM employees."""

from datetime import datetime, timezone
from uuid import uuid4

import auth
import crm
import db as store
import users

MANAGERS = {"director", "operations", "sales_head", "dispatcher"}


class InboxError(Exception):
    def __init__(self, status: int, detail: str):
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
            if lead_id and not crm.get_record(tx, "leads", lead_id):
                raise InboxError(404, "Лид не найден")
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

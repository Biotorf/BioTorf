"""Department assignments, independent of personal CRM reminders."""

import re
from contextlib import closing
from datetime import timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import AwareDatetime, BaseModel, Field, StrictInt

import crm
import db
import users

router = APIRouter(prefix="/api/department-tasks")
COLLECTION = "_department_tasks"
DEPARTMENTS = {
    "production": {"production"},
    "marketing": {"marketing"},
    "sales": {"sales_head", "sales", "dispatcher"},
}
MANAGEMENT = {"director", "operations"}
Status = Literal["new", "working", "blocked", "done", "cancelled"]


class ProductionLine(BaseModel):
    productId: str = Field(min_length=1, max_length=120)
    quantity: StrictInt = Field(gt=0, le=1_000_000_000)


class TaskCreate(BaseModel):
    department: Literal["production", "marketing", "sales"]
    coordinator: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    deadline: AwareDatetime
    items: list[ProductionLine] = Field(default_factory=list, max_length=50)


class TaskChange(BaseModel):
    revision: str
    assignee: str | None = Field(default=None, min_length=1, max_length=120)
    deadline: AwareDatetime | None = None
    status: Status | None = None
    progress: StrictInt | None = Field(default=None, ge=0, le=100)
    completed: dict[str, StrictInt] | None = None
    note: str | None = Field(default=None, max_length=2000)


def _manage(request, task):
    return (request.state.role in MANAGEMENT or
            (task["coordinator"] == request.state.user
             and request.state.role in DEPARTMENTS[task["department"]]))


def _execute(request, task):
    return (task.get("assignee") == request.state.user
            and request.state.role in DEPARTMENTS[task["department"]])


def _present(request, task):
    return {**task, "canAssign": _manage(request, task),
            "canReport": _manage(request, task) or _execute(request, task)}


def _employee(conn, login, department):
    employee = conn.execute("SELECT login, role, active FROM users WHERE login=?", (login,)).fetchone()
    if not employee or not employee["active"] or employee["role"] not in DEPARTMENTS[department]:
        raise HTTPException(422, "Выберите активного сотрудника выбранного отдела.")
    return employee["login"]


@router.get("")
def list_tasks(request: Request):
    management = request.state.role in MANAGEMENT
    with closing(db.connect()) as conn:
        visible = [_present(request, task) for task in crm.list_records(conn, COLLECTION)
                   if _manage(request, task) or _execute(request, task)]
    managed = set(DEPARTMENTS) if management else {task["department"] for task in visible if task["canAssign"]}
    visible_logins = {login for task in visible for login in (task["createdBy"], task["coordinator"], task.get("assignee"))}
    staff = []
    for employee in users.list_all():
        department = next((key for key, roles in DEPARTMENTS.items() if employee["role"] in roles), None)
        if employee["login"] in visible_logins or (employee["active"] and department in managed):
            staff.append({"login": employee["login"], "name": employee["name"],
                          "department": department, "active": bool(employee["active"])})
    return {"items": visible, "employees": staff, "canCreate": management}


@router.post("", status_code=201)
def create_task(body: TaskCreate, request: Request):
    if request.state.role not in MANAGEMENT:
        raise HTTPException(403, "Поручения отделам выдаёт руководство.")
    if not body.title.strip():
        raise HTTPException(422, "Укажите название задачи.")
    if (body.department == "production") != bool(body.items):
        raise HTTPException(422, "Для производства добавьте хотя бы одну позицию выпуска.")
    if len({item.productId for item in body.items}) != len(body.items):
        raise HTTPException(422, "Укажите каждый товар одной строкой.")
    with closing(db.connect()) as conn, crm.write_transaction(conn) as tx:
        coordinator = _employee(tx, body.coordinator, body.department)
        items = []
        for item in body.items:
            product = crm.get_record(tx, "skus", item.productId) or {}
            name = str(product.get("name") or "")
            line = str(product.get("line") or "").strip().casefold()
            if line not in {"agro", "home"}:
                match = re.search(r"\b(agro|home)\b", name, re.IGNORECASE)
                line = match[1].casefold() if match else ""
            try:
                pack = float(str(product.get("pack", "")).replace(",", "."))
            except ValueError:
                pack = 0
            if not line or not 0 < pack < float("inf"):
                raise HTTPException(422, "Выберите товар Agro или Home с фасовкой в литрах.")
            items.append({**item.model_dump(), "name": name, "line": line.title(),
                          "pack": pack, "completed": 0})
        task_id = "DT-" + uuid4().hex
        saved = crm._write(tx, COLLECTION, {
            "id": task_id, "department": body.department, "coordinator": coordinator,
            "title": body.title.strip(), "description": body.description.strip(),
            "deadline": body.deadline.astimezone(timezone.utc).isoformat(),
            "createdBy": request.state.user, "createdAt": crm._now(),
            "assignee": None, "status": "new", "progress": 0, "items": items,
            "completedAt": None, "note": "",
        }, task_id)
    return _present(request, saved)


@router.patch("/{task_id}")
def change_task(task_id: str, body: TaskChange, request: Request):
    with closing(db.connect()) as conn, crm.write_transaction(conn) as tx:
        task = crm.get_record(tx, COLLECTION, task_id)
        if not task or not (_manage(request, task) or _execute(request, task)):
            raise HTTPException(404, "Задача не найдена.")
        if task["_updatedAt"] != body.revision:
            raise HTTPException(409, "Задача обновилась. Загрузите её ещё раз.")
        can_manage = _manage(request, task)
        if (body.assignee is not None or body.deadline is not None or body.status == "cancelled") and not can_manage:
            raise HTTPException(403, "Назначение, срок и отмена доступны ответственному за отдел или руководству.")
        if task["status"] in {"done", "cancelled"}:
            raise HTTPException(409, "Задача уже закрыта.")
        if body.assignee is not None:
            task["assignee"] = _employee(tx, body.assignee, task["department"])
        if body.deadline is not None:
            task["deadline"] = body.deadline.astimezone(timezone.utc).isoformat()
        if body.status is not None:
            task["status"] = body.status
        if body.note is not None:
            task["note"] = body.note.strip()
        if not task["assignee"] and task["status"] in {"working", "blocked", "done"}:
            raise HTTPException(422, "Сначала назначьте исполнителя.")
        if task["status"] == "blocked" and not task["note"]:
            raise HTTPException(422, "Укажите причину задержки.")
        if task["items"]:
            if body.completed is not None:
                limits = {item["productId"]: item["quantity"] for item in task["items"]}
                if any(key not in limits or not 0 <= value <= limits[key] for key, value in body.completed.items()):
                    raise HTTPException(422, "Факт выпуска должен быть в пределах плана каждой позиции.")
                for item in task["items"]:
                    item["completed"] = body.completed.get(item["productId"], item["completed"])
            done = sum(item["completed"] for item in task["items"])
            total = sum(item["quantity"] for item in task["items"])
            task["progress"] = done * 100 // total
            if task["status"] == "done" and done != total:
                raise HTTPException(422, "Для завершения укажите полный выпуск по всем позициям.")
        elif task["status"] == "done":
            task["progress"] = 100
        elif body.progress is not None:
            task["progress"] = body.progress
        if task["status"] == "done":
            task["completedAt"] = crm._now()
        saved = crm._write(tx, COLLECTION, crm._record_data(task, task_id), task_id)
    return _present(request, saved)

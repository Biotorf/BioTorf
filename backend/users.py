"""Реестр сотрудников BIOTORF Business OS (SQLite, таблица users).

Зачем: раньше вход в систему был только по общему паролю AUTH_PASSWORD —
любой сотрудник получал одну и ту же роль, и зарегистрироваться через
фронтенд было нельзя. Теперь:

  • POST /auth/register — первая регистрация автоматически получает роль
    «director» (Генеральный директор); все последующие — «pending»
    (ожидает подтверждения) без прав, пока гендиректор не выдаст роль
    через PUT /api/users/{login}/role;
  • пароли хранятся как pbkdf2_sha256$итерации$salt$hash — сам пароль
    сотрудника сервер не знает и не может отдать;
  • таблица lives in the same comms.db (volume /data) — переживает пересборку.

Роль «pending» отсутствует в auth.ROLES → middleware отклоняет любые
запросы /api/* такого пользователя с 403 («ждёт подтверждения»), при этом
он видит список сотрудников и свою карточку через GET /api/users (read-all).
"""

import hashlib
import hmac
import re
import secrets
import time
from datetime import datetime, timezone

import auth
import db as store

MIN_PASSWORD_LEN = 8
PBKDF2_ITERATIONS = 120_000
NAME_RE = re.compile(r"^[\w\-.\s]{2,64}$", re.UNICODE)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


SCHEMA_USERS = """
CREATE TABLE IF NOT EXISTS users (
    login         TEXT PRIMARY KEY,
    name          TEXT NOT NULL DEFAULT '',
    role          TEXT NOT NULL DEFAULT 'pending',
    pw_hash       TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL DEFAULT '',
    active        INTEGER NOT NULL DEFAULT 1,
    position      TEXT NOT NULL DEFAULT '',
    phone         TEXT NOT NULL DEFAULT '',
    email         TEXT NOT NULL DEFAULT '',
    note          TEXT NOT NULL DEFAULT '',
    token_version INTEGER NOT NULL DEFAULT 0
);
"""

# профильные поля, которые сотрудник может заполнить о себе сам
PROFILE_FIELDS = ("name", "position", "phone", "email", "note")
PROFILE_MAX_LEN = {"name": 64, "position": 64, "phone": 32, "email": 64, "note": 500}


def init_tables(conn) -> None:
    conn.executescript(SCHEMA_USERS)
    # миграция для существующих БД: добавляем колонки, если их нет
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
    for col in ("position", "phone", "email", "note"):
        if col not in cols:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")
    if "token_version" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0")


# ── хеширование паролей (pbkdf2-hmac-sha256, stdlib) ─────────────────────────
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt),
                             PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iters, salt, hexhash = stored.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", (password or "").encode(),
                                 bytes.fromhex(salt), int(iters))
        return hmac.compare_digest(dk.hex(), hexhash)
    except Exception:
        return False


# ── доступ к таблице ─────────────────────────────────────────────────────────
def get(login: str) -> dict | None:
    with store.connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE login=?", (login,)).fetchone()
    return dict(row) if row else None


def list_all() -> list[dict]:
    with store.connect() as conn:
        rows = conn.execute(
            "SELECT login, name, role, created_at, active, position, phone, email "
            "FROM users "
            "ORDER BY CASE WHEN role='director' THEN 0 ELSE 1 END, created_at"
        ).fetchall()
    return [dict(r) for r in rows]


def count() -> int:
    with store.connect() as conn:
        return conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]


def create(login: str, name: str, password: str, role: str) -> dict:
    login_n = norm_login(login)
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO users (login, name, role, pw_hash, created_at, active) "
            "VALUES (?,?,?,?,?,1)",
            (login_n, name, role, hash_password(password), _now()),
        )
    return {"login": login_n, "name": name, "role": role,
            "roleName": auth.ROLES.get(role, "Ожидает подтверждения"),
            "created_at": _now()}


def set_role(login: str, role: str) -> dict | None:
    with store.connect() as conn:
        cur = conn.execute("UPDATE users SET role=? WHERE login=?", (role, login))
        if cur.rowcount == 0:
            return None
        row = conn.execute(
            "SELECT login, name, role, created_at, active FROM users WHERE login=?",
            (login,)).fetchone()
    d = dict(row)
    d["roleName"] = auth.ROLES.get(d["role"], "Ожидает подтверждения")
    return d


def change_password(login: str, old_password: str, new_password: str) -> tuple[int, dict]:
    """Смена собственного пароля (только по старому паролю)."""
    u = get(norm_login(login))
    if not u:
        return 404, {"detail": "Сотрудник не найден"}
    if not verify_password(old_password or "", u["pw_hash"]):
        return 401, {"detail": "Текущий пароль указан неверно"}
    if len(new_password or "") < MIN_PASSWORD_LEN:
        return 400, {"detail": f"Новый пароль не короче {MIN_PASSWORD_LEN} символов"}
    with store.connect() as conn:
        conn.execute("UPDATE users SET pw_hash=?, token_version=token_version+1 "
                     "WHERE login=?", (hash_password(new_password), u["login"]))
    return 200, {"ok": True}


def delete(login: str) -> bool:
    with store.connect() as conn:
        cur = conn.execute("DELETE FROM users WHERE login=?", (login,))
        return cur.rowcount > 0


def norm_login(login: str) -> str:
    return (login or "").strip()[:64]


# ── бизнес-логика регистрации / входа ────────────────────────────────────────
def register(login: str, name: str, password: str) -> tuple[int, dict]:
    """Регистрация нового сотрудника.

    Первый аккаунт в системе автоматически становится «director» (генеральный
    директор) — это заявленное поведение. Остальные получают роль «pending» и
    ждут, пока директор выдаст роль. Возвращает (http-код, тело).
    """
    login_n = norm_login(login)
    name = (name or "").strip()[:64] or login_n
    if not auth.NAME_RE.match(login_n):
        return 400, {"detail": "Логин: 2–64 символа (буквы, цифры, - . _ пробел)"}
    if not NAME_RE.match(name):
        return 400, {"detail": "Имя: 2–64 символа"}
    if len(password or "") < MIN_PASSWORD_LEN:
        return 400, {"detail": f"Пароль должен быть не короче {MIN_PASSWORD_LEN} символов"}
    if get(login_n):
        return 409, {"detail": "Такой логин уже зарегистрирован"}
    is_first = count() == 0
    role = "director" if is_first else "pending"
    try:
        user = create(login_n, name, password, role)
    except Exception as e:  # гонка двух «первых» регистраций и т.п.
        if "UNIQUE" in str(e).upper():
            return 409, {"detail": "Такой логин уже зарегистрирован"}
        raise
    return 201, {"ok": True, "firstAccount": is_first, **user}


def authenticate(login: str, password: str) -> dict | None:
    """Проверка логина/пароля. Успех → токен + профиль; ошибка → None."""
    u = get(norm_login(login))
    if not u or not u.get("active"):
        # константное время против орacles'ов «существует ли логин»:
        time.sleep(0.05)
        return None
    if not verify_password(password or "", u["pw_hash"]):
        return None
    if u["role"] not in auth.ROLES:      # pending и пр. — пускать в API нельзя
        return {"pending": True, "login": u["login"], "name": u["name"],
                "role": u["role"]}
    return {"token": auth.make_token(u["login"], u["role"],
                                     token_version=u.get("token_version", 0)),
            "user": u["login"], "name": u["name"], "role": u["role"],
            "roleName": auth.ROLES[u["role"]], "roles": auth.ROLES,
            "expiresIn": auth.AUTH_TOKEN_TTL}


# ── профиль сотрудника (заполняет сам сотрудник через мини-профиль) ──────────
def update_profile(login: str, data: dict) -> tuple[int, dict]:
    """PATCH профиля: name/position/phone/email/note. Возвращает (код, тело)."""
    login_n = norm_login(login)
    u = get(login_n)
    if not u:
        return 404, {"detail": "Сотрудник не найден"}
    upd, vals = [], []
    for field in PROFILE_FIELDS:
        if field not in data:
            continue
        val = (data.get(field) or "").strip()[:PROFILE_MAX_LEN[field]]
        if field == "name":
            if not NAME_RE.match(val or u["name"] or login_n):
                return 400, {"detail": "Имя: 2–64 символа"}
            val = val or login_n
        if field == "email" and val and "@" not in val:
            return 400, {"detail": "Некорректный e-mail"}
        if field == "phone" and val and not re.match(r"^[+\d\s()-]{5,32}$", val):
            return 400, {"detail": "Телефон: цифры, пробелы, +, -, ()"}
        upd.append(f"{field}=?")
        vals.append(val)
    if not upd:
        return 400, {"detail": "Нет обновляемых полей"}
    with store.connect() as conn:
        conn.execute(f"UPDATE users SET {', '.join(upd)} WHERE login=?",
                     (*vals, login_n))
        row = conn.execute("SELECT * FROM users WHERE login=?", (login_n,)).fetchone()
    d = dict(row)
    d.pop("pw_hash", None)
    d["roleName"] = auth.ROLES.get(d["role"], "Ожидает подтверждения")
    return 200, {"ok": True, **d}


def bump_token_version(login: str) -> int:
    """Инкремент версии токена: все ранее выданные токены становятся невалидны
    (смена роли директором / удаление аккаунта = мгновенный отзыв доступа)."""
    with store.connect() as conn:
        conn.execute("UPDATE users SET token_version = token_version + 1 "
                     "WHERE login=?", (norm_login(login),))
        row = conn.execute("SELECT token_version v FROM users WHERE login=?",
                           (norm_login(login),)).fetchone()
    return int(row["v"]) if row else 0

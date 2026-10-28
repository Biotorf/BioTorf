"""Telegram getUpdates-воркер — мост между Bot API и Comms API.

Telegram не даёт webhook без публичного HTTPS, поэтому воркер работает с любого
хоста: long-poll через getUpdates -> пересылка апдейтов в POST /webhooks/telegram.

Запуск:
    TELEGRAM_BOT_TOKEN=<токен из @BotFather> \
    TELEGRAM_WEBHOOK_SECRET=<тот же секрет, что в .env> \
    python telegram_worker.py [--api http://127.0.0.1:8787]

Токен бота и секрет вебхука берутся ИЗ ФАЙЛА .env (TELEGRAM_BOT_TOKEN,
TELEGRAM_WEBHOOK_SECRET) — как в ранней версии, когда отдельной вкладки
«Каналы CRM» ещё не было. Никаких обращений к CRM за секретами: тот механизм
(worker-token / with_token / сервисная учётка «worker») нестабильно проходил
авторизацию middleware и порождал вечные 401 — удалён полностью.

Чтобы бот получал сообщения с телефонами контактов:
    @BotFather -> /setprivacy -> Disable  (или используйте личные чаты)
    и включите share_phone: см. request_contact ниже.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

# ВАЖНО: 127.0.0.1 внутри контейнера воркера — это сам воркер, а не бэкенд.
# Дефолт — docker-DNS имя сервиса backend; при --api localhost/127.0.0.1
# автоматически переписываем на backend (лечит «Name or service not known»
# и вечные 401 у старых контейнеров, собранных с битым дефолтом).
API = os.environ.get("COMMS_API", "http://backend:8787")


def _normalize_api(url: str) -> str:
    u = (url or "").strip().rstrip("/") or "http://backend:8787"
    for bad in ("127.0.0.1", "localhost", "0.0.0.0"):
        if f"://{bad}" in u:
            u = u.replace(f"://{bad}", "://backend")
    return u


API = _normalize_api(API)
ENV_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()  # основной источник токена (.env)
WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")    # секрет вебхука (.env)
API_KEY = os.environ.get("CRM_API_KEY", "").strip()  # необязательный статический ключ (legacy-режим)
OFFSET = 0


# ── токен бота и секрет вебхука — строго из файла .env (как в ранней версии) ──
# Механизм получения секретов из CRM через вкладку «Каналы» (эндпоинт
# /api/internal/worker-token, сервисная учётка «worker», with_token=1) удалён:
# он зависел от JWT-middleware и порождал вечные 401 у tg-воркера. Воркер
# больше НИКОГДА не запрашивает секреты у CRM; для обращений к /api/*
# используется Authorization, который middleware принимает в режиме общего
# пароля AUTH_PASSWORD (или DEV_MODE=1).


def _wait_backend(timeout_s: float = 60.0) -> bool:
    """Дождаться готовности CRM API (health). Возвращает True, если дождались.

    Лечит гонку при старте стека: DNS-имя «backend» появляется только когда
    контейнер бэкенда запущен, а первые попытки без ожидания дают
    «Name or service not known» и выход с кодом 1 (restart-шторм)."""
    deadline = time.time() + timeout_s
    i = 0
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{API.rstrip('/')}/health", timeout=3) as r:
                if r.status == 200:
                    if i:
                        print(f"[tg-worker] backend доступен: {API}", file=sys.stderr)
                    return True
        except Exception:
            pass
        i += 1
        if i == 1:
            print(f"[tg-worker] ждём запуска backend ({API}) ...", file=sys.stderr)
        time.sleep(1.0)
    print(f"[tg-worker] ВНИМАНИЕ: backend за 60 сек не поднялся ({API})", file=sys.stderr)
    return False


def _auth_headers() -> dict:
    """Заголовок Authorization для /api/* CRM.

    Ранняя схема: воркер работает в режиме общего пароля — middleware бэкенда
    принимает любой непустой Bearer-токен, когда сотрудники ещё не
    зарегистрированы, либо токен сотрудника, выданный POST /auth/login по
    AUTH_PASSWORD. Поэтому: 1) явный CRM_API_KEY из .env; 2) штатный логин
    worker@biotorf.local c паролем AUTH_PASSWORD (если задан); 3) fallback —
    сам AUTH_PASSWORD (старое поведение legacy-воркера)."""
    if API_KEY:
        return {"Authorization": f"Bearer {API_KEY}"}
    pw = os.environ.get("AUTH_PASSWORD", "").strip()
    if not pw:
        return {}
    tok = _login_for_password(pw)
    return {"Authorization": f"Bearer {tok}"} if tok else {}


_LOGIN_CACHE = {"tok": "", "exp": 0.0}


def _login_for_password(pw: str) -> str:
    """Получить штатный JWT через POST /auth/login (кэш ~9 мин из TTL 12 ч)."""
    now = time.time()
    if _LOGIN_CACHE["tok"] and _LOGIN_CACHE["exp"] > now:
        return _LOGIN_CACHE["tok"]
    try:
        body = json.dumps({"login": "worker@biotorf.local", "password": pw}).encode()
        req = urllib.request.Request(
            f"{API.rstrip('/')}/auth/login", data=body, method="POST",
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            tok = (json.loads(resp.read() or b"{}").get("token") or "").strip()
        if tok:
            _LOGIN_CACHE["tok"] = tok
            _LOGIN_CACHE["exp"] = now + 540
            return tok
    except Exception as e:
        print(f"[tg-worker] /auth/login не выполнен ({e}) — использую пароль как Bearer",
              file=sys.stderr)
    return pw  # legacy-режим: режим общего пароля принимает любой Bearer


def _get_json_auth(path: str) -> dict:
    for attempt in (1, 2, 3):
        req = urllib.request.Request(
            f"{API.rstrip('/')}{path}", headers=_auth_headers())
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as e:
            if e.code in (401, 403) and attempt < 3:
                # токен протух/пуст (перезапуск бэкенда, смена AUTH_SECRET или
                # гонка при старте) — сбрасываем кэш логина, ждём backend, повторяем
                _LOGIN_CACHE["tok"] = ""
                _LOGIN_CACHE["exp"] = 0.0
                if attempt == 2:
                    _wait_backend()
                continue
            raise
        except urllib.error.URLError:
            # DNS/соединение: backend ещё не поднялся — подождём и повторим
            if attempt < 3:
                _wait_backend()
                continue
            raise
    return {}


def resolve_webhook_secret() -> str:
    """Секрет вебхука Telegram — из TELEGRAM_WEBHOOK_SECRET в .env."""
    return WEBHOOK_SECRET


def resolve_bot_token() -> str:
    """Токен бота — из TELEGRAM_BOT_TOKEN в .env."""
    return ENV_BOT_TOKEN


def post_json(url: str, payload: dict, headers: dict | None = None) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read() or b"{}")


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.loads(resp.read() or b"{}")


def send_to_user(chat_id, text: str, voice_path: str | None = None, bot_token: str | None = None):
    """sendMessage (или sendVoice для голосовых) от имени бота; (ok, message_id, ошибка)."""
    BOT_TOKEN = bot_token or resolve_bot_token()
    try:
        if voice_path:
            ok, msg_id, err = _send_voice_multipart(chat_id, voice_path)
            if ok or "400" not in str(err or ""):
                return ok, msg_id, err
            # Telegram отверг голосовое — fallback: обычный текст-заглушка
        res = post_json(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            {"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
        )
        if res.get("ok"):
            return True, res["result"].get("message_id"), None
        return False, None, res.get("description", "unknown")
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="ignore")[:300]
        print(f"[tg-worker] sendMessage error: {e.code} {body}", file=sys.stderr)
        return False, None, f"HTTP {e.code}: {body}"
    except Exception as e:
        print(f"[tg-worker] sendMessage error: {e}", file=sys.stderr)
        return False, None, str(e)


def _send_voice_multipart(chat_id, path: str, bot_token: str | None = None):
    BOT_TOKEN = bot_token or resolve_bot_token()
    """Bot API принимает файлы только multipart/form-data (не JSON)."""
    import uuid
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendVoice"
    boundary = "----biotorfw" + uuid.uuid4().hex[:12]
    data = open(path, "rb").read()
    parts = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat_id}\r\n".encode(),
        (f"--{boundary}\r\nContent-Disposition: form-data; name=\"voice\"; filename=\"voice.oga\"\r\n"
         f"Content-Type: audio/ogg\r\n\r\n").encode(),
        data,
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    req = urllib.request.Request(
        url, data=b"".join(parts),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            res = json.loads(resp.read() or b"{}")
        if res.get("ok"):
            return True, res["result"].get("message_id"), None
        return False, None, res.get("description", "unknown")
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="ignore")[:300]
        return False, None, f"HTTP {e.code}: {body}"


def resolve_media_path(media_id: str, api: str):
    """Скачать медиафайл с Comms API во временный файл для отправки в Bot API."""
    import re as _re
    import tempfile
    if not media_id or not _re.fullmatch(r"[A-Za-z0-9_-]{4,64}", media_id):
        return None
    try:
        req = urllib.request.Request(f"{api}/api/media/{media_id}",
                                     headers=_auth_headers())
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read(20 * 1024 * 1024)
        if not data:
            return None
        fd, p = tempfile.mkstemp(suffix=".oga", prefix="tgvoice_")
        os.write(fd, data)
        os.close(fd)
        return p
    except Exception as e:
        print(f"[tg-worker] media download failed ({media_id}): {e}", file=sys.stderr)
        return None


def deliver_outbox(api: str):
    """Доставка исходящих ответов, созданных в ленте CRM (/api/comms/outbox).

    Бот может писать только пользователям, которые сами начали с ним диалог,
    поэтому отправка живёт здесь (long-poll-сторона), а не в API-сервере."""
    try:
        data = _get_json_auth("/api/comms/outbox?kind=telegram&limit=20")
    except Exception as e:
        print(f"[tg-worker] outbox fetch skip: {e}", file=sys.stderr)
        return
    for item in data.get("items", []):
        payload = item.get("payload") or {}
        chat_id = payload.get("chatId") or payload.get("userIndex")
        if not chat_id:
            continue
        # голосовые сообщения: если к записи привязан медиафайл — качаем его с
        # Comms API и отправляем через sendVoice (Telegram покажет плеер)
        voice_path = None
        media = payload.get("media") or {}
        if media.get("mediaId"):
            voice_path = resolve_media_path(media["mediaId"], api)
        ok, msg_id, err = send_to_user(chat_id, item.get("text") or "", voice_path)
        if voice_path:
            try:
                os.unlink(voice_path)
            except OSError:
                pass
        try:
            post_json(
                f"{api}/api/comms/{item['id']}/delivered",
                {"ok": ok, "messageId": msg_id, "error": err},
                headers=_auth_headers(),
            )
        except Exception as e:
            print(f"[tg-worker] delivered mark failed: {e}", file=sys.stderr)
        if ok:
            print(f"[tg-worker] доставлен ответ {item['id']} в чат {chat_id}")
        else:
            print(f"[tg-worker] НЕ доставлен {item['id']} в чат {chat_id}: {err}", file=sys.stderr)


def main():
    global OFFSET, WEBHOOK_SECRET, API
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default=API, help="базовый URL Comms API")
    parser.add_argument("--once", action="store_true", help="один цикл getUpdates и выход (для теста)")
    args = parser.parse_args()

    # --api тоже нормализуем: localhost/127.0.0.1 внутри контейнера воркера —
    # это сам воркер, а не бэкенд (отсюда «Name or service not known»/401)
    API = _normalize_api(args.api)
    args.api = API

    # ждём подъёма backend: DNS-имя «backend» появляется только когда его
    # контейнер запущен; без этого первые попытки падают и воркер
    # выходил с кодом 1 в restart-шторм
    _wait_backend()

    # токен бота и секрет вебхука — из файла .env (TELEGRAM_BOT_TOKEN,
    # TELEGRAM_WEBHOOK_SECRET), как в ранней версии проекта
    BOT_TOKEN = resolve_bot_token()
    WEBHOOK_SECRET = resolve_webhook_secret()

    if not BOT_TOKEN:
        sys.exit(
            "[tg-worker] ОШИБКА: TELEGRAM_BOT_TOKEN не задан. Впишите токен из "
            "@BotFather в переменную TELEGRAM_BOT_TOKEN файла .env, затем: "
            "docker compose --profile tg up -d --force-recreate telegram-worker"
        )
    if not WEBHOOK_SECRET:
        sys.exit("[tg-worker] ОШИБКА: не задан секрет вебхука — заполните "
                 "TELEGRAM_WEBHOOK_SECRET в .env")
    print(f"[tg-worker] старт, токен выглядит как {BOT_TOKEN[:12]}...{BOT_TOKEN[-4:]}")

    # Сбрасываем webhook, если он был назначен ранее — иначе getUpdates вернёт ошибку 409.
    try:
        with urllib.request.urlopen(
            f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook", timeout=15
        ) as resp:
            json.loads(resp.read())
    except Exception as e:
        print(f"[tg-worker] deleteWebhook skip: {e}", file=sys.stderr)

    print(f"[tg-worker] polling -> {args.api}/webhooks/telegram")
    last_outbox = 0.0
    while True:
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?timeout=25&offset={OFFSET}"
            with urllib.request.urlopen(url, timeout=40) as resp:
                data = json.loads(resp.read())
            for upd in data.get("result", []):
                OFFSET = max(OFFSET, upd["update_id"] + 1)
                res = post_json(
                    f"{args.api}/webhooks/telegram", upd,
                    headers={"X-Bot-Secret": WEBHOOK_SECRET},
                )
                print(f"[tg-worker] update {upd['update_id']} -> {res}")
        except Exception as e:
            print(f"[tg-worker] error: {e}", file=sys.stderr)
            time.sleep(3)
        # раз в ~10 секунд проверяем очередь исходящих ответов из CRM
        if time.time() - last_outbox >= 10:
            last_outbox = time.time()
            deliver_outbox(args.api)
        if args.once:
            break


if __name__ == "__main__":
    main()

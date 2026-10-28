"""Telegram getUpdates-воркер — мост между Bot API и Comms API.

Telegram не даёт webhook без публичного HTTPS, поэтому воркер работает с любого
хоста: long-poll через getUpdates -> пересылка апдейтов в POST /webhooks/telegram.

Запуск:
    TELEGRAM_WEBHOOK_SECRET=<тот же секрет, что в .env> \
    python telegram_worker.py [--api http://127.0.0.1:8787]

Токен бота берётся из подключённого аккаунта Telegram («Настройки → Каналы»,
хранится в БД); переменная окружения TELEGRAM_BOT_TOKEN — необязательный
fallback для локальной разработки.

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
ENV_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()  # fallback для локальной разработки
WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
API_KEY = os.environ.get("CRM_API_KEY", "").strip()   # явный сервисный токен (необязателен)
OFFSET = 0
_TOKEN_CACHE = {"tok": "", "exp": 0.0}


def service_token() -> str:
    """Сервисный JWT для обращений воркера к CRM API.

    Порядок: 1) явный CRM_API_KEY из env; 2) внутренний эндпоинт
    GET /api/internal/worker-token (доступен только из docker-сети),
    кэшируется до истечения TTL."""
    if API_KEY:
        return API_KEY
    now = time.time()
    # прошлый токен принимаем только если он реально ещё жив (запас 30 сек),
    # иначе при смене AUTH_SECRET/перезапуске бэкенда вечно получаем 401
    if _TOKEN_CACHE["tok"] and _TOKEN_CACHE["exp"] - 30 > now:
        return _TOKEN_CACHE["tok"]
    try:
        with urllib.request.urlopen(
                f"{API.rstrip('/')}/api/internal/worker-token", timeout=10) as resp:
            tok = (json.loads(resp.read() or b"{}").get("token") or "").strip()
        if tok:
            _TOKEN_CACHE["tok"] = tok
            _TOKEN_CACHE["exp"] = now + 540  # TTL 10 мин, обновляем за 9
            return tok
    except urllib.error.URLError as e:
        # DNS/соединение: чаще всего неверный COMMS_API/--api (например,
        # http://127.0.0.1:8787 внутри контейнера = сам воркер, а не бэкенд)
        print(f"[tg-worker] worker-token недоступен ({API}): {e.reason} — "
              f"проверьте, что контейнер backend запущен и доступен по имени «backend»",
              file=sys.stderr)
    except Exception as e:
        print(f"[tg-worker] worker-token недоступен ({API}): {e}", file=sys.stderr)
    return ""


def _auth_headers() -> dict:
    tok = service_token()
    return {"Authorization": f"Bearer {tok}"} if tok else {}


def _get_json_auth(path: str) -> dict:
    for attempt in (1, 2):
        req = urllib.request.Request(
            f"{API.rstrip('/')}{path}", headers=_auth_headers())
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as e:
            if e.code == 401 and attempt == 1:
                # сервисный токен протух (перезапуск бэкенда / смена секрета) —
                # берём свежий и повторяем запрос один раз
                _TOKEN_CACHE["tok"] = ""
                _TOKEN_CACHE["exp"] = 0.0
                continue
            raise
    return {}


def resolve_webhook_secret() -> str:
    """Секрет вебхука Telegram: привязанный аккаунт из CRM
    (GET /api/channels/telegram/secrets, доступен только сервисному субу
    «worker»), затем env-fallback TELEGRAM_WEBHOOK_SECRET."""
    try:
        data = _get_json_auth("/api/channels/telegram/secrets")
        sec = (data.get("secret") or "").strip()
        if sec:
            return sec
    except Exception as e:
        print(f"[tg-worker] не удалось получить секрет из CRM ({e}) — пробую env",
              file=sys.stderr)
    return WEBHOOK_SECRET


def resolve_bot_token() -> str:
    """Токен бота: сначала аккаунт Telegram из CRM (GET /api/channels/telegram/accounts,
    токен отдаётся только с авторизацией), затем env-fallback."""
    try:
        data = _get_json_auth("/api/channels/telegram/accounts?with_token=1")
        for acc in (data.get("items") or data.get("accounts") or []):
            tok = (acc.get("token") or "").strip()
            if tok and acc.get("status", "active") == "active":
                return tok
    except Exception as e:
        print(f"[tg-worker] не удалось получить токен из CRM ({e}) — пробую env", file=sys.stderr)
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

    # токен и секрет берём из подключённого аккаунта Telegram в CRM
    # («Настройки → Каналы»), env — только fallback для локальной разработки
    BOT_TOKEN = resolve_bot_token()
    WEBHOOK_SECRET = resolve_webhook_secret()

    if not BOT_TOKEN:
        sys.exit(
            "[tg-worker] ОШИБКА: токен бота не найден. Подключите аккаунт Telegram "
            "в CRM («Каналы → Telegram → Подключить») или задайте TELEGRAM_BOT_TOKEN "
            "и CRM_API_KEY в .env, затем: docker compose --profile tg up -d --force-recreate telegram-worker"
        )
    if not WEBHOOK_SECRET:
        sys.exit("[tg-worker] ОШИБКА: не задан секрет вебхука (секрет аккаунта Telegram в CRM "
                 "или TELEGRAM_WEBHOOK_SECRET в .env)")
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

"""Telegram getUpdates-воркер — мост между Bot API и Comms API.

Telegram не даёт webhook без публичного HTTPS, поэтому воркер работает с любого
хоста: long-poll через getUpdates -> пересылка апдейтов в POST /webhooks/telegram.

Запуск (нужен bot-токен от @BotFather):
    TELEGRAM_BOT_TOKEN=123:ABC... TELEGRAM_WEBHOOK_SECRET=<тот же секрет, что в backend/.env> \
    python telegram_worker.py [--api http://127.0.0.1:8787]

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

API = os.environ.get("COMMS_API", "http://127.0.0.1:8787")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
OFFSET = 0


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


def send_to_user(chat_id, text: str, voice_path: str | None = None):
    """sendMessage (или sendVoice для голосовых) от имени бота; (ok, message_id, ошибка)."""
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


def _send_voice_multipart(chat_id, path: str):
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
        with urllib.request.urlopen(f"{api}/api/media/{media_id}", timeout=30) as resp:
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
        data = get_json(f"{api}/api/comms/outbox?kind=telegram&limit=20")
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
            )
        except Exception as e:
            print(f"[tg-worker] delivered mark failed: {e}", file=sys.stderr)
        if ok:
            print(f"[tg-worker] доставлен ответ {item['id']} в чат {chat_id}")
        else:
            print(f"[tg-worker] НЕ доставлен {item['id']} в чат {chat_id}: {err}", file=sys.stderr)


def main():
    global OFFSET
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default=API, help="базовый URL Comms API")
    parser.add_argument("--once", action="store_true", help="один цикл getUpdates и выход (для теста)")
    args = parser.parse_args()

    if not BOT_TOKEN or not BOT_TOKEN.strip():
        sys.exit(
            "[tg-worker] ОШИБКА: TELEGRAM_BOT_TOKEN пуст. "
            "Впишите токен от @BotFather в файл .env рядом с docker-compose.yml "
            "и выполните: docker compose --profile tg up -d --force-recreate telegram-worker"
        )
    if not WEBHOOK_SECRET:
        sys.exit("[tg-worker] ОШИБКА: не задан TELEGRAM_WEBHOOK_SECRET")
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

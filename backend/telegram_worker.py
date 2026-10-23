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


def main():
    global OFFSET
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default=API, help="базовый URL Comms API")
    parser.add_argument("--once", action="store_true", help="один цикл getUpdates и выход (для теста)")
    args = parser.parse_args()

    if not BOT_TOKEN:
        sys.exit("Не задан TELEGRAM_BOT_TOKEN")
    if not WEBHOOK_SECRET:
        sys.exit("Не задан TELEGRAM_WEBHOOK_SECRET")

    print(f"[tg-worker] polling -> {args.api}/webhooks/telegram")
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
        if args.once:
            break


if __name__ == "__main__":
    main()

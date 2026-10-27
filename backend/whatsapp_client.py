"""Обёртка WhatsApp Cloud API (Graph API) — исходящая отправка сообщений.

Используется только stdlib (urllib), как и остальной бэкенд: никаких лишних
зависимостей в контейнере.

Чтобы заработала реальная отправка, заполните в .env (пробрасывается в backend):
    WHATSAPP_TOKEN          — постоянный Access Token (System User token) из
                              Meta Business Suite / WhatsApp API Keys
    WHATSAPP_PHONE_NUMBER_ID— id вашего бизнес-номера (Phones -> ID, цифры)

Эндпоинт Graph API v21.0:
    POST https://graph.facebook.com/v21.0/{phone_number_id}/messages
"""

import json
import urllib.error
import urllib.request

GRAPH_VERSION = "v21.0"


class WhatsAppError(Exception):
    """Ошибка WhatsApp Cloud API с человекочитаемым описанием."""

    def __init__(self, message: str, status: int | None = None, code: int | None = None):
        super().__init__(message)
        self.status = status
        self.code = code


def send_message(token: str, phone_number_id: str, to: str, text: str) -> dict:
    """Отправить текстовое сообщение клиенту в WhatsApp.

    Возвращает ответ Graph API: {"messages": [{"id": "wamid..."}], ...}.
    Бросает WhatsAppError при любой проблеме (разбор ответа Meta).
    """
    if not token or not phone_number_id:
        raise WhatsAppError("WhatsApp не настроен на сервере (WHATSAPP_TOKEN / WHATSAPP_PHONE_NUMBER_ID пусты)")

    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": "".join(ch for ch in (to or "") if ch.isdigit()),  # Meta принимает только цифры
        "type": "text",
        "text": {"preview_url": False, "body": text},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    try:
        # таймаут 5с (был 15с): синхронные исходящие вызовы выполняются в
        # threadpool uvicorn — зависшие запросы к Meta не должны блокировать
        # рабочие потоки и приводить к 502 на всех эндпоинтах
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="ignore")
        try:
            err = json.loads(body).get("error", {})
            msg = err.get("message") or body[:300]
            code = err.get("code")
        except Exception:
            msg, code = body[:300], None
        raise WhatsAppError(f"Meta не приняла сообщение: {msg}", status=e.code, code=code) from e
    except Exception as e:  # сеть/таймауты
        raise WhatsAppError(f"Нет связи с Graph API: {e}") from e


def check_config(token: str, phone_number_id: str) -> dict:
    """Проверка конфигурации при старте backend: GET /{phone_number_id}?fields=id,display_phone_number.

    Возвращает dict с полями ok/error/phone — результат пишется в логи и
    влияет на capabilities.whatsappSend.
    """
    if not token or not phone_number_id:
        return {"ok": False, "error": "WHATSAPP_TOKEN или WHATSAPP_PHONE_NUMBER_ID не заданы"}
    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{phone_number_id}?fields=id,display_phone_number"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:   # был 15с — см. send_text
            data = json.loads(resp.read() or b"{}")
        return {"ok": True, "phone": data.get("display_phone_number"), "id": data.get("id")}
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="ignore")
        try:
            msg = json.loads(body).get("error", {}).get("message", body[:200])
        except Exception:
            msg = body[:200]
        return {"ok": False, "error": f"Meta отвергла токен/номер ({e.code}): {msg}"}
    except Exception as e:
        return {"ok": False, "error": f"Нет связи с Graph API: {e}"}

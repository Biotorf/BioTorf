"""Локальный smoke-тест бэкенда (имитация условий Docker). Запуск: python3 _smoke.py

Проверяет: /health, приём входящего звонка через вебхук телефонии, автопривязку
по номеру к хозяйству из farms.json, пропущенные звонки, идемпотентность (защиту
от дублей) и 401 на неверный токен.
"""
import os, tempfile, json

tmp = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(tmp, "comms.db")
# farms.json как в Docker — bind-mount существующего файла
os.environ["FARMS_FILE"] = os.path.join(tmp, "farms.json")
open(os.environ["FARMS_FILE"], "w").write(json.dumps(
    [{"id": "F-001", "name": "Тест", "phone": "+996700112233"}]))
os.environ["TELEPHONY_TOKEN"] = "t"

import db as store
store.init_db()   # в приложении это делает startup-хук; здесь — явно до запросов

import main  # noqa
from fastapi.testclient import TestClient

CDR = {"call_id": "x1", "direction": "inbound", "from": "+996700112233",
       "to": "+996312000000", "status": "answered", "duration": 42,
       "ts": "2026-10-24T10:00:00Z"}

with TestClient(main.app) as c:   # контекст выполняет startup-события
    assert c.get("/health").json()["ok"] is True, "health"

    r = c.post("/webhooks/telephony?token=t", json=CDR)
    assert r.status_code == 200, r.text

    def items():
        lst = c.get("/api/comms").json()
        return lst["items"] if isinstance(lst, dict) else lst

    its = items()
    assert len(its) == 1, its
    assert its[0].get("farmId") == "F-001", f"автопривязка не сработала: {its[0]}"

    # пропущенный входящий звонок
    missed = dict(CDR, call_id="x2", **{"from": "+996555443322", "status": "missed", "duration": 0})
    assert c.post("/webhooks/telephony?token=t", json=missed).status_code == 200

    # повторная доставка того же CDR — дубль игнорируется (идемпотентность)
    c.post("/webhooks/telephony?token=t", json=CDR)
    assert len(items()) == 2, f"ожидалось 2 записи, получено {len(items())}"

    # неверный токен -> 401
    bad = c.post("/webhooks/telephony?token=bad", json={"call_id": "y",
               "direction": "outbound", "from": "a", "to": "b"})
    assert bad.status_code == 401, bad.status_code

print("SMOKE OK: health / звонок+автопривязка / пропущенный / идемпотентность / 401")


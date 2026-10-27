"""Кэш реестра хозяйств (farms.json) с отслеживанием изменений по mtime.

Раньше auto_link()/auto_link_handle() перечитывали и парсили farms.json на
каждый входящий звонок/сообщение (webhook-шторм = шторм дисковых чтений).
Теперь файл читается один раз; повторное чтение происходит только если
изменилась метка времени файла (админ обновил реестр или фронт сделал
экспорт snapshot) — актуальность сохраняется, стоимость — нет.

Дополнительно строится индекс по нормализованным телефонам и @username,
поиск O(1) вместо линейного сканирования всего реестра.
"""

import json
import re
import threading
from pathlib import Path

_lock = threading.Lock()
_cache: dict = {"path": None, "mtime": None, "size": None,
                "by_phone": {}, "by_tg": {}}


def _digits(s) -> str:
    return re.sub(r"\D", "", s or "")


def _norm_tg(v) -> str:
    return str(v or "").lstrip("@").strip().lower()


def _load(path: Path) -> dict:
    by_phone, by_tg = {}, {}
    try:
        farms = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(farms, list):
            farms = []
        for f in farms:
            if not isinstance(f, dict) or not f.get("id"):
                continue
            d = _digits(f.get("phone"))
            if len(d) >= 6:
                by_phone.setdefault(d, f["id"])
            t = _norm_tg(f.get("telegram"))
            if t:
                by_tg.setdefault(t, f["id"])
    except Exception as e:
        print(f"[farms] не удалось прочитать {path}: {e}")
    return {"by_phone": by_phone, "by_tg": by_tg}


def _refresh_if_stale(path: Path) -> None:
    try:
        st = path.stat()
        key = (str(path), st.st_mtime_ns, st.st_size)
    except OSError:
        key = (str(path), None, None)
    if (_cache["path"], _cache["mtime"], _cache["size"]) == key:
        return
    with _lock:
        if (_cache["path"], _cache["mtime"], _cache["size"]) == key:
            return
        idx = _load(path) if key[1] is not None else {"by_phone": {}, "by_tg": {}}
        _cache.update(path=key[0], mtime=key[1], size=key[2], **idx)


def link_by_phone(path: Path, phone: str | None) -> str | None:
    """farmId хозяйства из реестра по номеру телефона (или None)."""
    d = _digits(phone)
    if len(d) < 6:
        return None
    _refresh_if_stale(path)
    return _cache["by_phone"].get(d)


def link_by_handle(path: Path, handle: str | None) -> str | None:
    """farmId хозяйства из реестра по telegram-username (или None)."""
    h = _norm_tg(handle)
    if not h:
        return None
    _refresh_if_stale(path)
    return _cache["by_tg"].get(h)

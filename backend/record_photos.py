"""Private image galleries attached to persistent CRM records."""

import hashlib
import json
from contextlib import closing
from datetime import datetime, timezone
from io import BytesIO
from threading import BoundedSemaphore
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from fastapi.routing import APIRoute
from PIL import Image, ImageOps

import auth
import crm
import db as store

COLLECTIONS = frozenset({"farms", "skus", "pilots", "production", "media", "applications", "contacts", "orders"})
MAX_BYTES = 8 * 1024 * 1024
MAX_REQUEST_BYTES = MAX_BYTES + 64 * 1024  # Зазор для заголовков и разделителей multipart.
MAX_PHOTOS = 12
MAX_PIXELS = 24_000_000
MAX_EDGE = 1800
THUMBNAIL_EDGE = 320
IMAGE_FORMATS = ("JPEG", "PNG", "WEBP")
IMAGE_MIME = "image/webp"
IMAGE_PROCESSORS = BoundedSemaphore(1)


class PhotoRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        if "POST" not in self.methods:
            return handler

        async def limited_upload(request: Request):
            length = request.headers.get("content-length", "")
            if length.isascii() and length.isdecimal() and int(length) > MAX_REQUEST_BYTES:
                raise HTTPException(413, "Размер фото превышает 8 МБ.")

            size = 0

            async def receive():
                nonlocal size
                message = await request.receive()
                size += len(message.get("body", b""))
                if size > MAX_REQUEST_BYTES:
                    raise HTTPException(413, "Размер фото превышает 8 МБ.")
                return message

            return await handler(Request(request.scope, receive))

        return limited_upload


router = APIRouter(prefix="/api/crm-photos", tags=["CRM photos"], route_class=PhotoRoute)

SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS crm_photos (
    id          TEXT PRIMARY KEY,
    coll        TEXT NOT NULL,
    record_id   TEXT NOT NULL,
    digest      TEXT NOT NULL,
    name        TEXT NOT NULL,
    size        INTEGER NOT NULL,
    width       INTEGER NOT NULL,
    height      INTEGER NOT NULL,
    is_cover    INTEGER NOT NULL CHECK (is_cover IN (0, 1)),
    created_at  TEXT NOT NULL,
    content     BLOB NOT NULL,
    thumbnail   BLOB NOT NULL,
    UNIQUE (coll, record_id, digest),
    FOREIGN KEY (coll, record_id) REFERENCES crm_records (coll, id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_crm_photos_cover ON crm_photos (coll, record_id) WHERE is_cover=1;
"""

PHOTO_COLUMNS = "p.id, p.name, p.size, p.width, p.height, p.is_cover, p.created_at"


def init_tables(conn) -> None:
    if not store.IS_POSTGRES:
        conn.executescript(SQLITE_SCHEMA)


def _check_collection(request: Request, collection: str) -> None:
    if request.state.user == "worker":
        raise HTTPException(403, "Фото доступны только сотрудникам CRM.")
    if collection not in COLLECTIONS:
        raise HTTPException(404, "Этот раздел не поддерживает фото.")


def _can_view_farm(request: Request, farm: dict | None) -> bool:
    if farm is None or request.state.role != "sales":
        return True
    staff_names = {request.state.user, getattr(request.state, "user_name", None), "Менеджер А"}
    return farm.get("owner") in staff_names - {None, ""}


def _require_record(conn, request: Request, collection: str, record_id: str, *, write=False) -> None:
    row = crm.get_record(conn, collection, record_id)
    if row is None:
        raise HTTPException(404, "Карточка не найдена.")
    if request.state.role == "sales":
        farm = row if collection == "farms" else (
            crm.get_record(conn, "farms", str(row["farmId"])) if row.get("farmId") else None
        )
        if not _can_view_farm(request, farm):
            raise HTTPException(404, "Карточка не найдена.")
    if write and not auth.can_write_crm_collection(request.state.role, collection):
        raise HTTPException(403, "Ваша роль может просматривать фото этой карточки.")


def _metadata(row) -> dict:
    return {
        "id": row["id"], "name": row["name"], "mime": IMAGE_MIME, "size": row["size"],
        "width": row["width"], "height": row["height"], "isCover": bool(row["is_cover"]),
        "createdAt": row["created_at"],
    }


def _gallery(conn, request: Request, collection: str, record_id: str) -> dict:
    rows = conn.execute(
        "SELECT " + PHOTO_COLUMNS + " FROM crm_photos p WHERE p.coll=? AND p.record_id=? "
        "ORDER BY p.is_cover DESC, p.created_at ASC, p.id ASC",
        (collection, record_id),
    ).fetchall()
    return {
        "items": [_metadata(row) for row in rows],
        "canEdit": auth.can_write_crm_collection(request.state.role, collection),
        "limit": MAX_PHOTOS, "maxBytes": MAX_BYTES,
    }


def _name(filename: str | None) -> str:
    name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    return "".join(char for char in name if char.isprintable()).strip()[:180] or "Фото"


def _encode(image: Image.Image, quality: int) -> bytes:
    output = BytesIO()
    image.save(output, format="WEBP", quality=quality)
    return output.getvalue()


def _prepare_image(raw: bytes) -> tuple[bytes, bytes, int, int]:
    try:
        with Image.open(BytesIO(raw), formats=IMAGE_FORMATS) as source:
            if source.width * source.height > MAX_PIXELS:
                raise HTTPException(422, "Фото должно быть не больше 24 мегапикселей.")
            if getattr(source, "is_animated", False):
                raise HTTPException(422, "Выберите обычное фото без анимации.")
            if source.format == "JPEG":
                source.draft("RGB", (MAX_EDGE, MAX_EDGE))
            alpha = "A" in source.getbands() or "transparency" in source.info
            ImageOps.exif_transpose(source, in_place=True)
            source.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)
            image = source.convert("RGBA" if alpha else "RGB")
            image.info.clear()
            width, height = image.size
            content = _encode(image, quality=84)
            image.thumbnail((THUMBNAIL_EDGE, THUMBNAIL_EDGE), Image.Resampling.LANCZOS)
            return content, _encode(image, quality=76), width, height
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
        raise HTTPException(422, "Не удалось открыть фото. Выберите целый файл JPG, PNG или WebP.") from exc


def _prepare_upload(file: UploadFile) -> tuple[str, bytes, bytes, int, int]:
    with IMAGE_PROCESSORS:
        raw = file.file.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise HTTPException(413, "Размер фото превышает 8 МБ.")
        return hashlib.sha256(raw).hexdigest(), *_prepare_image(raw)


@router.get("/{collection}")
def list_covers(request: Request, collection: str, id: list[str] = Query(max_length=100)):
    _check_collection(request, collection)
    ids = list(dict.fromkeys(id))
    if not ids:
        return {"items": {}}
    placeholders = ",".join("?" for _ in ids)
    with closing(store.connect()) as conn:
        rows = conn.execute(
            "SELECT " + PHOTO_COLUMNS + ", p.record_id, r.data AS record_data "
            "FROM crm_photos p JOIN crm_records r ON r.coll=p.coll AND r.id=p.record_id "
            "WHERE p.coll=? AND p.is_cover=1 AND p.record_id IN (" + placeholders + ")",
            (collection, *ids),
        ).fetchall()
        if request.state.role != "sales":
            return {"items": {row["record_id"]: _metadata(row) for row in rows}}
        pairs = [(row, json.loads(row["record_data"])) for row in rows]
        if collection == "farms":
            return {"items": {row["record_id"]: _metadata(row) for row, farm in pairs if _can_view_farm(request, farm)}}
        farm_ids = {str(record["farmId"]) for _, record in pairs if record.get("farmId")}
        farms = {}
        if farm_ids:
            placeholders = ",".join("?" for _ in farm_ids)
            farms = {row["id"]: json.loads(row["data"]) for row in conn.execute(
                "SELECT id, data FROM crm_records WHERE coll='farms' AND id IN (" + placeholders + ")",
                tuple(farm_ids),
            ).fetchall()}
        return {"items": {
            row["record_id"]: _metadata(row) for row, record in pairs
            if _can_view_farm(request, farms.get(str(record.get("farmId"))))
        }}


@router.get("/{collection}/{record_id}")
def list_photos(request: Request, collection: str, record_id: str):
    _check_collection(request, collection)
    with closing(store.connect()) as conn:
        _require_record(conn, request, collection, record_id)
        return _gallery(conn, request, collection, record_id)


@router.post("/{collection}/{record_id}", status_code=201)
def upload_photo(request: Request, collection: str, record_id: str, file: UploadFile = File(...)):
    _check_collection(request, collection)
    if file.size is not None and file.size > MAX_BYTES:
        raise HTTPException(413, "Размер фото превышает 8 МБ.")
    with closing(store.connect()) as conn:
        _require_record(conn, request, collection, record_id, write=True)
    digest, content, thumbnail, width, height = _prepare_upload(file)
    with closing(store.connect()) as conn, crm.write_transaction(conn) as tx:
        _require_record(tx, request, collection, record_id, write=True)
        rows = tx.execute("SELECT digest FROM crm_photos WHERE coll=? AND record_id=?", (collection, record_id)).fetchall()
        if any(row["digest"] == digest for row in rows):
            return _gallery(tx, request, collection, record_id)
        if len(rows) >= MAX_PHOTOS:
            raise HTTPException(409, "В карточке уже 12 фото. Удалите одно, чтобы добавить другое.")
        tx.execute(
            "INSERT INTO crm_photos (id, coll, record_id, digest, name, size, width, height, is_cover, created_at, content, thumbnail) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (uuid4().hex, collection, record_id, digest, _name(file.filename), len(content), width, height,
             int(not rows), datetime.now(timezone.utc).isoformat(), content, thumbnail),
        )
        return _gallery(tx, request, collection, record_id)


@router.patch("/{collection}/{record_id}/{photo_id}")
def choose_cover(request: Request, collection: str, record_id: str, photo_id: str):
    _check_collection(request, collection)
    with closing(store.connect()) as conn, crm.write_transaction(conn) as tx:
        _require_record(tx, request, collection, record_id, write=True)
        photo = tx.execute("SELECT is_cover FROM crm_photos WHERE coll=? AND record_id=? AND id=?",
                           (collection, record_id, photo_id)).fetchone()
        if photo is None:
            raise HTTPException(404, "Фото не найдено.")
        if not photo["is_cover"]:
            tx.execute("UPDATE crm_photos SET is_cover=0 WHERE coll=? AND record_id=? AND is_cover=1",
                       (collection, record_id))
            tx.execute("UPDATE crm_photos SET is_cover=1 WHERE coll=? AND record_id=? AND id=?",
                       (collection, record_id, photo_id))
        return _gallery(tx, request, collection, record_id)


@router.delete("/{collection}/{record_id}/{photo_id}")
def remove_photo(request: Request, collection: str, record_id: str, photo_id: str):
    _check_collection(request, collection)
    with closing(store.connect()) as conn, crm.write_transaction(conn) as tx:
        _require_record(tx, request, collection, record_id, write=True)
        removed = tx.execute(
            "DELETE FROM crm_photos WHERE coll=? AND record_id=? AND id=? RETURNING is_cover",
            (collection, record_id, photo_id),
        ).fetchone()
        if removed and removed["is_cover"]:
            tx.execute(
                "UPDATE crm_photos SET is_cover=1 WHERE id=(SELECT id FROM crm_photos "
                "WHERE coll=? AND record_id=? ORDER BY created_at ASC, id ASC LIMIT 1)",
                (collection, record_id),
            )
        return _gallery(tx, request, collection, record_id)


@router.get("/{collection}/{record_id}/{photo_id}/content")
def get_photo(request: Request, collection: str, record_id: str, photo_id: str, thumbnail: bool = False):
    _check_collection(request, collection)
    with closing(store.connect()) as conn:
        _require_record(conn, request, collection, record_id)
        field = "thumbnail" if thumbnail else "content"
        row = conn.execute("SELECT " + field + " FROM crm_photos WHERE coll=? AND record_id=? AND id=?",
                           (collection, record_id, photo_id)).fetchone()
    if row is None:
        raise HTTPException(404, "Фото не найдено.")
    return Response(bytes(row[0]), media_type=IMAGE_MIME, headers={
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
    })

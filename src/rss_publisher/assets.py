from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image
from .config import Settings

_ACTIVE_BLOCKED = {"text/html", "application/xhtml+xml", "image/svg+xml"}


def detect_type(path: Path, supplied: str | None = None) -> tuple[str, int | None, int | None, str]:
    with path.open("rb") as fh:
        head = fh.read(64)
    width = height = None
    ext = "bin"
    if head.startswith(b"%PDF-"):
        return "application/pdf", None, None, "pdf"
    try:
        with Image.open(path) as im:
            width, height = im.size
            fmt = (im.format or "").upper()
            mapping = {
                "PNG": ("image/png", "png"), "JPEG": ("image/jpeg", "jpg"),
                "WEBP": ("image/webp", "webp"), "GIF": ("image/gif", "gif"),
                "AVIF": ("image/avif", "avif"),
            }
            if fmt in mapping:
                mime, ext = mapping[fmt]
                return mime, width, height, ext
    except Exception:
        pass
    if len(head) > 12 and head[4:8] == b"ftyp":
        return "video/mp4", None, None, "mp4"
    if head.startswith(b"ID3") or (len(head) > 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
        return "audio/mpeg", None, None, "mp3"
    if supplied in _ACTIVE_BLOCKED:
        return supplied, None, None, "bin"
    if supplied and supplied.startswith(("audio/", "video/", "application/", "text/plain")):
        ext_map = {"application/zip": "zip", "text/plain": "txt", "application/json": "json"}
        return supplied, None, None, ext_map.get(supplied, "bin")
    return "application/octet-stream", None, None, "bin"


def ingest_temp_file(settings: Settings, temp_path: Path, filename: str | None, supplied_mime: str | None) -> dict:
    size = temp_path.stat().st_size
    if size > settings.max_upload_bytes:
        raise ValueError(f"asset exceeds max upload size ({settings.max_upload_bytes} bytes)")
    digest = hashlib.sha256()
    with temp_path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    sha = digest.hexdigest()
    mime, width, height, ext = detect_type(temp_path, supplied_mime)
    if mime in _ACTIVE_BLOCKED:
        raise ValueError(f"active web content is not accepted as a public asset: {mime}")
    bucket = settings.media_path if mime.startswith(("image/", "audio/", "video/")) else settings.files_path
    relative = f"{bucket}/{sha[:2]}/{sha[2:4]}/{sha}.{ext}"
    storage = settings.public_dir / relative.lstrip("/")
    storage.parent.mkdir(parents=True, exist_ok=True)
    if not storage.exists():
        shutil.copyfile(temp_path, storage)
    return {
        "id": f"asset:sha256:{sha}",
        "sha256": sha,
        "original_filename": filename,
        "mime_type": mime,
        "size_bytes": size,
        "width": width,
        "height": height,
        "public_path": relative,
        "storage_path": str(storage),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def temp_file_from_stream(stream, max_bytes: int) -> Path:
    fd, name = tempfile.mkstemp(prefix="rss-publisher-upload-")
    total = 0
    try:
        with os.fdopen(fd, "wb") as out:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError(f"asset exceeds max upload size ({max_bytes} bytes)")
                out.write(chunk)
        return Path(name)
    except Exception:
        try:
            os.unlink(name)
        except OSError:
            pass
        raise

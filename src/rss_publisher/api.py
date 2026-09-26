from __future__ import annotations

import os
import tempfile
from pathlib import Path
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse
import uvicorn

from .config import Settings
from .service import PublisherService

settings = Settings.from_env()
service = PublisherService(settings)
app = FastAPI(title="RSS Publisher Asset API", version="0.1.0")


def authorize(authorization: str | None = Header(default=None)) -> None:
    if settings.auth_mode == "none":
        return
    expected = f"Bearer {settings.api_token}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Bearer token required")


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    try:
        service.get_feed()
        settings.public_dir.mkdir(parents=True, exist_ok=True)
        test = settings.public_dir / ".ready"
        test.write_text("ok")
        test.unlink(missing_ok=True)
        return {"status": "ready"}
    except Exception as exc:
        return JSONResponse(status_code=503, content={"status": "not_ready", "error": str(exc)})


@app.get("/api/v1/service")
def service_info():
    return {
        "name": "RSS Publisher",
        "version": "0.1.0",
        "publication": {
            "base_url": settings.public_base_url,
            "feed_url": settings.feed_url,
            "media_url": settings.absolute(settings.media_path + "/"),
            "files_url": settings.absolute(settings.files_path + "/"),
        },
        "uploads": {
            "url": settings.upload_url,
            "max_size_bytes": settings.max_upload_bytes,
            "authentication": settings.auth_mode,
        },
    }


@app.post("/api/v1/assets", dependencies=[Depends(authorize)])
async def upload_asset(file: UploadFile = File(...)):
    fd, name = tempfile.mkstemp(prefix="rss-upload-")
    path = Path(name)
    total = 0
    try:
        with os.fdopen(fd, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > settings.max_upload_bytes:
                    raise HTTPException(status_code=413, detail="upload too large")
                out.write(chunk)
        try:
            return service.add_asset(path, file.filename, file.content_type)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        path.unlink(missing_ok=True)


@app.get("/api/v1/assets/{asset_id:path}", dependencies=[Depends(authorize)])
def asset_metadata(asset_id: str):
    asset = service.get_asset(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="asset not found")
    return asset


def main() -> None:
    host = os.getenv("RSS_API_LISTEN_HOST", "127.0.0.1")
    port = int(os.getenv("RSS_API_LISTEN_PORT", "8765"))
    uvicorn.run("rss_publisher.api:app", host=host, port=port, log_level=os.getenv("RSS_LOG_LEVEL", "info").lower())

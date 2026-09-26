from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    public_dir: Path
    public_base_url: str
    feed_path: str = "/feed.xml"
    entry_path: str = "/entries"
    media_path: str = "/media"
    files_path: str = "/files"
    auth_mode: str = "none"
    api_token: str = ""
    max_upload_bytes: int = 100 * 1024 * 1024
    orphan_asset_ttl_seconds: int = 7 * 24 * 3600
    embeddings_enabled: bool = False
    embeddings_base_url: str = ""
    embeddings_api_key: str = ""
    embeddings_model: str = ""
    embeddings_dimensions: int | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        base = os.getenv("RSS_PUBLIC_BASE_URL", "http://localhost:8080").rstrip("/")
        parsed = urlparse(base)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("RSS_PUBLIC_BASE_URL must be an absolute http(s) URL")
        auth_mode = os.getenv("RSS_AUTH_MODE", "none").strip().lower()
        if auth_mode not in {"none", "bearer"}:
            raise ValueError("RSS_AUTH_MODE must be 'none' or 'bearer'")
        token = os.getenv("RSS_API_TOKEN", "")
        if auth_mode == "bearer" and not token:
            raise ValueError("RSS_API_TOKEN is required when RSS_AUTH_MODE=bearer")
        dims = os.getenv("RSS_EMBEDDINGS_DIMENSIONS", "").strip()
        return cls(
            data_dir=Path(os.getenv("RSS_DATA_DIR", "/data")),
            public_dir=Path(os.getenv("RSS_PUBLIC_DIR", "/srv/public")),
            public_base_url=base,
            feed_path=_path(os.getenv("RSS_FEED_PATH", "/feed.xml")),
            entry_path=_path(os.getenv("RSS_ENTRY_PATH", "/entries")),
            media_path=_path(os.getenv("RSS_MEDIA_PATH", "/media")),
            files_path=_path(os.getenv("RSS_FILES_PATH", "/files")),
            auth_mode=auth_mode,
            api_token=token,
            max_upload_bytes=int(os.getenv("RSS_MAX_UPLOAD_BYTES", str(100 * 1024 * 1024))),
            orphan_asset_ttl_seconds=int(os.getenv("RSS_ORPHAN_ASSET_TTL_SECONDS", str(7 * 24 * 3600))),
            embeddings_enabled=_bool("RSS_EMBEDDINGS_ENABLED", False),
            embeddings_base_url=os.getenv("RSS_EMBEDDINGS_BASE_URL", "").rstrip("/"),
            embeddings_api_key=os.getenv("RSS_EMBEDDINGS_API_KEY", ""),
            embeddings_model=os.getenv("RSS_EMBEDDINGS_MODEL", ""),
            embeddings_dimensions=int(dims) if dims else None,
        )

    @property
    def db_path(self) -> Path:
        return self.data_dir / "publisher.db"

    def absolute(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return self.public_base_url + _path(path)

    @property
    def feed_url(self) -> str:
        return self.absolute(self.feed_path)

    @property
    def upload_url(self) -> str:
        return self.absolute("/api/v1/assets")


def _path(value: str) -> str:
    value = value.strip()
    if not value.startswith("/"):
        value = "/" + value
    return value.rstrip("/") if value != "/" else value


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}

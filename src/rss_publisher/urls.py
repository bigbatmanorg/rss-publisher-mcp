from __future__ import annotations

from urllib.parse import urlparse
from .config import Settings


def normalize_url(settings: Settings, value: str | None, *, base_path: str | None = None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme:
        if parsed.scheme not in {"http", "https"}:
            raise ValueError(f"unsupported URL scheme: {parsed.scheme}")
        return value
    if value.startswith("/"):
        return settings.public_base_url + value
    prefix = base_path or ""
    if prefix:
        prefix = "/" + prefix.strip("/")
    return settings.public_base_url + prefix + "/" + value.lstrip("/")


def is_privateish_url(value: str) -> bool:
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local") or host.startswith("10.") or host.startswith("192.168.") or host.startswith("172.16.")

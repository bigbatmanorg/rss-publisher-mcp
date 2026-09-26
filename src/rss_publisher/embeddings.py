from __future__ import annotations

import hashlib
import json
import math
from typing import Callable
import httpx
from .config import Settings
from .models import FeedEntry


def semantic_text(entry: FeedEntry, body_limit: int = 3000) -> str:
    body = entry.content_text or ""
    if not body and entry.content_html:
        import re
        body = re.sub(r"<[^>]+>", " ", entry.content_html)
    parts = [
        f"Kind: {entry.kind}",
        f"Title: {entry.title or ''}",
        f"Summary: {entry.summary or ''}",
        f"Categories: {', '.join(entry.categories)}",
        f"Content: {' '.join(body.split())[:body_limit]}",
    ]
    selected = {k: v for k, v in entry.public_metadata.items() if isinstance(v, (str, int, float, bool))}
    if selected:
        parts.append("Metadata: " + json.dumps(selected, sort_keys=True, ensure_ascii=False))
    return "\n".join(parts)


def semantic_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class EmbeddingProvider:
    def __init__(self, settings: Settings, transport: Callable[[str], list[float]] | None = None):
        self.settings = settings
        self.transport = transport

    def embed(self, text: str) -> list[float]:
        if self.transport:
            return self.transport(text)
        if not self.settings.embeddings_enabled:
            raise RuntimeError("embeddings are disabled")
        if not self.settings.embeddings_base_url or not self.settings.embeddings_model:
            raise RuntimeError("embedding endpoint/model is not configured")
        headers = {"Content-Type": "application/json"}
        if self.settings.embeddings_api_key:
            headers["Authorization"] = f"Bearer {self.settings.embeddings_api_key}"
        payload: dict = {"model": self.settings.embeddings_model, "input": text}
        if self.settings.embeddings_dimensions:
            payload["dimensions"] = self.settings.embeddings_dimensions
        response = httpx.post(
            self.settings.embeddings_base_url + "/embeddings",
            json=payload,
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        return [float(x) for x in response.json()["data"][0]["embedding"]]


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0

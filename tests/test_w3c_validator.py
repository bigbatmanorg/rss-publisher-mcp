from __future__ import annotations

import os

import httpx
import pytest
from PIL import Image

from rss_publisher.config import Settings
from rss_publisher.service import PublisherService

pytestmark = pytest.mark.skipif(
    os.getenv("RSS_RUN_NETWORK_TESTS", "").strip().lower() not in {"1", "true", "yes", "on"},
    reason="network integration test disabled (set RSS_RUN_NETWORK_TESTS=1)",
)

VALIDATOR_URL = "https://validator.w3.org/feed/check.cgi"


def _representative_feed(tmp_path) -> bytes:
    settings = Settings(
        data_dir=tmp_path / "data",
        public_dir=tmp_path / "public",
        public_base_url="https://rss.example.test",
        embeddings_enabled=False,
    )
    service = PublisherService(settings)
    service.configure_feed({
        "title": "Example Feed",
        "description": "A representative feed",
        "site_url": "https://rss.example.test",
        "copyright": "(c) 2026 Example",
        "categories": ["News"],
    })
    image = tmp_path / "hero.png"
    Image.new("RGB", (1200, 630)).save(image)
    asset = service.add_asset(image, "hero.png", "image/png")
    service.create_entry({
        "id": "urn:uuid:11111111-2222-3333-4444-555555555555",
        "kind": "article",
        "title": "Rich Article",
        "summary": "A summary.",
        "content_html": "<p>Full <strong>body</strong>.</p>",
        "published_at": "2026-09-26T09:00:00Z",
        "updated_at": "2026-09-26T10:00:00Z",
        "authors": [{"name": "News Desk"}],
        "categories": ["Security", "PAM"],
        "links": [{"rel": "related", "title": "More", "url": "https://more.example/a"}],
        "hero_image": {"asset_id": asset["id"], "alt": "Hero"},
    })
    return (settings.public_dir / "feed.xml").read_bytes()


def test_representative_feed_passes_w3c_validator(tmp_path):
    feed = _representative_feed(tmp_path)
    response = httpx.post(
        VALIDATOR_URL,
        data={"rawdata": feed.decode("utf-8"), "output": "soap12"},
        timeout=60,
    )
    response.raise_for_status()
    body = response.text
    assert "<m:validity>true</m:validity>" in body, body[:2000]

from __future__ import annotations

import pytest
from pydantic import ValidationError

from rss_publisher.models import AssetRef, Enclosure, FeedConfig, FeedEntry


def test_entry_requires_readable_content_unless_draft():
    with pytest.raises(ValidationError, match="needs title"):
        FeedEntry(id="urn:uuid:x")
    # Drafts may be empty.
    assert FeedEntry(id="urn:uuid:x", lifecycle="draft").lifecycle == "draft"


def test_categories_are_deduplicated_case_insensitively():
    entry = FeedEntry(title="T", summary="x", categories=["Security", "security", "  PAM  ", ""])
    assert entry.categories == ["Security", "PAM"]


def test_asset_ref_requires_locator():
    with pytest.raises(ValidationError, match="asset_id or url"):
        AssetRef(alt="no locator")


def test_enclosure_requires_locator():
    with pytest.raises(ValidationError, match="asset_id or url"):
        Enclosure(mime_type="audio/mpeg", size_bytes=1)


def test_extra_fields_are_forbidden():
    with pytest.raises(ValidationError):
        FeedEntry(title="T", summary="x", unexpected=True)


def test_feed_config_max_items_must_be_positive():
    with pytest.raises(ValidationError, match="max_items"):
        FeedConfig(max_items=0)


def test_feed_config_defaults():
    config = FeedConfig()
    assert config.max_items == 200
    assert config.language == "en"
    assert config.ttl_minutes == 20


def test_entry_has_at_most_one_primary_enclosure():
    # The schema exposes a single optional enclosure, so a second one cannot be
    # represented; this guards the "one native enclosure maximum" release gate.
    entry = FeedEntry(
        title="T", summary="x",
        primary_enclosure={"url": "https://e.example/a.mp3", "mime_type": "audio/mpeg", "size_bytes": 1},
    )
    assert entry.primary_enclosure is not None
    assert not isinstance(entry.primary_enclosure, list)
    with pytest.raises(ValidationError):
        FeedEntry(
            title="T", summary="x",
            primary_enclosure=[
                {"url": "https://e.example/a.mp3", "mime_type": "audio/mpeg", "size_bytes": 1},
                {"url": "https://e.example/b.mp3", "mime_type": "audio/mpeg", "size_bytes": 2},
            ],
        )

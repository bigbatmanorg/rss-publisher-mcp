from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest
from PIL import Image

from rss_publisher.models import FeedConfig, FeedEntry
from rss_publisher.renderer import (
    build_full_html,
    local_permalink,
    render_entry_page,
    render_feed,
    render_index,
    resolve_asset_url,
    stable_slug,
)


def _lookup(assets):
    return lambda asset_id: assets.get(asset_id)


def test_stable_slug_is_deterministic_and_sanitized():
    entry = FeedEntry(id="urn:uuid:ABCDEF12-3456-7890-abcd-ef1234567890", title="Hello, World! 2026")
    slug = stable_slug(entry)
    assert slug == stable_slug(entry)
    assert slug.startswith("hello-world-2026-")
    assert " " not in slug


def test_stable_slug_falls_back_when_title_empty():
    entry = FeedEntry(id="urn:uuid:00000000-0000-0000-0000-000000000000", kind="note", summary="x")
    assert stable_slug(entry).startswith("note-")


def test_local_permalink_uses_stored_path(settings):
    entry = FeedEntry(id="urn:uuid:1", title="T", summary="x", private_metadata={"local_permalink_path": "/entries/custom"})
    assert local_permalink(settings, entry) == "https://rss.example.test/entries/custom"


def test_local_permalink_falls_back_to_slug(settings):
    entry = FeedEntry(id="urn:uuid:22222222-2222-2222-2222-222222222222", title="Fallback", summary="x")
    assert local_permalink(settings, entry).startswith("https://rss.example.test/entries/fallback-")


def test_resolve_asset_url_unknown_asset_raises(settings):
    entry = FeedEntry(id="urn:uuid:1", title="T", summary="x", hero_image={"asset_id": "asset:sha256:nope"})
    with pytest.raises(ValueError, match="unknown asset"):
        resolve_asset_url(settings, entry.hero_image, _lookup({}))


def test_render_feed_includes_channel_extras(settings):
    config = FeedConfig(
        title="Extras", description="d", site_url="https://site.example",
        feed_url="https://site.example/feed.xml", copyright="(c) 2026",
        logo_url="/media/logo.png", categories=["News"], ttl_minutes=15,
        websub_hub_url="https://hub.example/",
    )
    xml = render_feed(settings, config, [], _lookup({}), __import__("datetime").datetime(2026, 9, 26, tzinfo=__import__("datetime").timezone.utc))
    text = xml.decode()
    assert "<copyright>(c) 2026</copyright>" in text
    assert "<ttl>15</ttl>" in text
    assert "<category>News</category>" in text
    assert "https://rss.example.test/media/logo.png" in text
    assert 'rel="hub"' in text
    assert 'rel="self"' in text


def test_render_feed_omits_ttl_when_none(settings):
    config = FeedConfig(title="NoTTL", description="d", ttl_minutes=None)
    xml = render_feed(settings, config, [], _lookup({}), __import__("datetime").datetime(2026, 9, 26, tzinfo=__import__("datetime").timezone.utc))
    assert b"<ttl>" not in xml


def test_render_feed_source_and_atom_links(settings):
    entry = FeedEntry(
        id="urn:uuid:33333333-3333-3333-3333-333333333333", title="Sourced", summary="x",
        origin_feed_url="https://origin.example/feed", origin_feed_title="Origin",
        links=[
            {"rel": "related", "url": "https://rel.example/a", "title": "Related"},
            {"rel": "via", "url": "https://via.example/b"},
            {"rel": "source", "url": "https://ignored.example/c"},
        ],
    )
    xml = render_feed(settings, FeedConfig(), [entry], _lookup({}), __import__("datetime").datetime(2026, 9, 26, tzinfo=__import__("datetime").timezone.utc)).decode()
    assert '<source url="https://origin.example/feed">Origin</source>' in xml
    assert 'rel="related"' in xml
    assert 'rel="via"' in xml
    # Only related/via/alternate become atom:link elements; source stays in the HTML body.
    assert '<atom:link href="https://ignored.example/c"' not in xml


def test_render_feed_media_attributes_and_enclosure(settings, tmp_path):
    image = tmp_path / "m.png"
    Image.new("RGB", (20, 10)).save(image)
    assets = {"asset:sha256:abc": {"public_path": "/media/ab/cd/abc.png", "mime_type": "image/png", "width": 20, "height": 10}}
    entry = FeedEntry(
        id="urn:uuid:44444444-4444-4444-4444-444444444444", title="Media", summary="x",
        media=[{"asset_id": "asset:sha256:abc", "title": "Pic", "credit": "Me", "duration_seconds": 12.9}],
        primary_enclosure={"asset_id": "asset:sha256:abc", "mime_type": "image/png", "size_bytes": 1234},
    )
    xml = render_feed(settings, FeedConfig(), [entry], _lookup(assets), __import__("datetime").datetime(2026, 9, 26, tzinfo=__import__("datetime").timezone.utc)).decode()
    assert 'medium="image"' in xml
    assert 'duration="12"' in xml
    assert "<media:title>Pic</media:title>" in xml
    assert "<media:credit>Me</media:credit>" in xml
    assert '<enclosure url="https://rss.example.test/media/ab/cd/abc.png" type="image/png" length="1234"' in xml


def test_render_feed_enclosure_url_only(settings):
    entry = FeedEntry(
        id="urn:uuid:55555555-5555-5555-5555-555555555555", title="Enc", summary="x",
        primary_enclosure={"url": "clip.mp4", "mime_type": "video/mp4", "size_bytes": 10},
    )
    xml = render_feed(settings, FeedConfig(), [entry], _lookup({}), __import__("datetime").datetime(2026, 9, 26, tzinfo=__import__("datetime").timezone.utc)).decode()
    assert "https://rss.example.test/files/clip.mp4" in xml


def test_render_feed_skips_non_emitted_lifecycles(settings):
    draft = FeedEntry(id="urn:uuid:66666666-6666-6666-6666-666666666666", title="Draft", summary="x", lifecycle="draft")
    archived = FeedEntry(id="urn:uuid:77777777-7777-7777-7777-777777777777", title="Archived", summary="x", lifecycle="archived")
    xml = render_feed(settings, FeedConfig(), [draft, archived], _lookup({}), __import__("datetime").datetime(2026, 9, 26, tzinfo=__import__("datetime").timezone.utc)).decode()
    assert "Draft" not in xml
    assert "Archived" not in xml


def test_build_full_html_retraction_and_correction(settings):
    entry = FeedEntry(
        id="urn:uuid:88888888-8888-8888-8888-888888888888", title="R", summary="x",
        lifecycle="retracted", correction_note="Was wrong", content_text="Body text",
    )
    html = build_full_html(settings, entry, _lookup({}))
    assert "Retracted." in html
    assert "Was wrong" in html
    assert "<p>Body text</p>" in html


def test_build_full_html_links_section(settings):
    entry = FeedEntry(
        id="urn:uuid:99999999-9999-9999-9999-999999999999", title="L", summary="x",
        links=[{"rel": "related", "url": "https://e.example/a", "title": "A"}],
    )
    html = build_full_html(settings, entry, _lookup({}))
    assert "<h2>Links</h2>" in html
    assert "https://e.example/a" in html


def test_build_full_html_returns_none_when_empty(settings):
    entry = FeedEntry(id="urn:uuid:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", title="Empty", summary="x")
    assert build_full_html(settings, entry, _lookup({})) is None


def test_render_entry_page_and_index(settings):
    entry = FeedEntry(id="urn:uuid:bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", title="Page", summary="Sum", content_text="Body")
    page = render_entry_page(settings, FeedConfig(title="Feed"), entry, _lookup({}))
    assert "<h1>Page</h1>" in page
    assert "Body" in page
    index = render_index(settings, FeedConfig(title="Feed"), [entry])
    assert "Page" in index
    assert "Subscribe to RSS" in index


def test_render_feed_output_parses(settings):
    entry = FeedEntry(id="urn:uuid:cccccccc-cccc-cccc-cccc-cccccccccccc", title="Parse", summary="x")
    xml = render_feed(settings, FeedConfig(), [entry], _lookup({}), __import__("datetime").datetime(2026, 9, 26, tzinfo=__import__("datetime").timezone.utc))
    root = ET.fromstring(xml)
    assert root.tag == "rss"

from pathlib import Path
import xml.etree.ElementTree as ET


def test_rich_entry_maps_to_expected_rss(service, tmp_path):
    result = service.create_entry({
        "id": "urn:uuid:22222222-2222-2222-2222-222222222222",
        "kind": "article",
        "title": "Security Story",
        "summary": "Short summary.",
        "content_html": "<p>Full <strong>story</strong>.</p><script>alert(1)</script>",
        "published_at": "2026-09-26T09:00:00Z",
        "updated_at": "2026-09-26T10:00:00Z",
        "authors": [{"name": "News Desk"}],
        "categories": ["Security", "PAM", "security"],
        "links": [{"rel": "source", "title": "Source", "url": "https://source.example/a"}],
        "public_metadata": {"priority": "high"},
    })
    xml = (service.settings.public_dir / "feed.xml").read_text()
    assert "<content:encoded>" in xml
    assert "&lt;p&gt;Full" in xml
    assert "alert(1)" not in xml
    assert "<dc:creator>News Desk</dc:creator>" in xml
    assert xml.count("<category>Security</category>") == 1
    assert "<category>PAM</category>" in xml
    assert "<rp:kind>article</rp:kind>" in xml
    assert "priority" in xml
    root = ET.fromstring(xml)
    assert root.tag == "rss"


def test_rebuild_is_byte_deterministic(service):
    service.create_entry({"id": "urn:uuid:33333333-3333-3333-3333-333333333333", "title": "Stable", "summary": "Stable output", "published_at": "2026-09-26T09:00:00Z"})
    feed = service.settings.public_dir / "feed.xml"
    first = feed.read_bytes()
    service.rebuild_public()
    second = feed.read_bytes()
    assert first == second


def test_local_permalink_does_not_change_when_title_changes(service):
    entry_id = "urn:uuid:44444444-4444-4444-4444-444444444444"
    service.create_entry({"id": entry_id, "title": "Initial Title", "summary": "x", "published_at": "2026-09-26T09:00:00Z"})
    before = service.get_entry(entry_id)["private_metadata"]["local_permalink_path"]
    service.update_entry(entry_id, {"title": "Completely Different Title"})
    after = service.get_entry(entry_id)["private_metadata"]["local_permalink_path"]
    assert before == after


def test_explicit_rebuild_does_not_touch_identical_feed_mtime(service):
    service.create_entry({"id": "urn:uuid:bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "title": "Stable Mtime", "summary": "x"})
    feed = service.settings.public_dir / "feed.xml"
    before = feed.stat().st_mtime_ns
    service.rebuild_public()
    assert feed.stat().st_mtime_ns == before

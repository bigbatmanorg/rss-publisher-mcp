from __future__ import annotations

import pytest
from PIL import Image

from rss_publisher.models import FeedEntry
from rss_publisher.service import PublisherService


def test_create_generates_uuid_and_timestamps(service):
    result = service.create_entry({"title": "Auto", "summary": "x"})
    assert result.id.startswith("urn:uuid:")
    entry = service.get_entry(result.id)
    assert entry["published_at"] is not None
    assert entry["updated_at"] == entry["published_at"]


def test_create_rejects_duplicate_id(service):
    service.create_entry({"id": "urn:uuid:dup", "title": "A", "summary": "x"})
    with pytest.raises(ValueError, match="already exists"):
        service.create_entry({"id": "urn:uuid:dup", "title": "B", "summary": "x"})


def test_create_rejects_duplicate_active_continuity_key(service):
    service.create_entry({"id": "urn:uuid:c1", "continuity_key": "k", "title": "A", "summary": "x"})
    with pytest.raises(ValueError, match="continuity_key already belongs"):
        service.create_entry({"id": "urn:uuid:c2", "continuity_key": "k", "title": "B", "summary": "x"})


def test_update_missing_entry_raises_keyerror(service):
    with pytest.raises(KeyError):
        service.update_entry("urn:uuid:missing", {"summary": "x"})


def test_update_ignores_null_id_in_patch(service):
    created = service.create_entry({"id": "urn:uuid:nullid", "title": "A", "summary": "x"})
    result = service.update_entry(created.id, {"id": None, "summary": "y"})
    assert result.status == "updated"
    assert service.get_entry(created.id)["id"] == created.id


def test_update_private_only_change_does_not_bump_updated_at(service):
    created = service.create_entry({"id": "urn:uuid:priv", "title": "A", "summary": "x"})
    before = service.get_entry(created.id)["updated_at"]
    result = service.update_entry(created.id, {"private_metadata": {"note": "internal"}})
    assert result.status == "updated"
    assert result.feed_changed is False
    assert service.get_entry(created.id)["updated_at"] == before


def test_correct_entry_sets_lifecycle_and_note(service):
    created = service.create_entry({"id": "urn:uuid:corr", "title": "A", "summary": "x"})
    result = service.correct_entry(created.id, "Fixed a typo", {"summary": "corrected"})
    assert result.status == "updated"
    entry = service.get_entry(created.id)
    assert entry["lifecycle"] == "corrected"
    assert entry["correction_note"] == "Fixed a typo"


def test_retract_without_reason(service):
    created = service.create_entry({"id": "urn:uuid:retr", "title": "A", "summary": "x"})
    result = service.retract_entry(created.id)
    assert result.status == "retracted"
    assert service.get_entry(created.id)["correction_note"] is None


def test_republish_non_archived_is_noop(service):
    created = service.create_entry({"id": "urn:uuid:rep", "title": "A", "summary": "x"})
    result = service.republish_entry(created.id)
    assert result.status == "unchanged"


def test_republish_missing_raises(service):
    with pytest.raises(KeyError):
        service.republish_entry("urn:uuid:missing")


def test_configure_feed_noop(service):
    result = service.configure_feed({"title": "RSS Publisher"})
    assert result.status == "unchanged"


def test_configure_feed_updates_and_rebuilds(service):
    result = service.configure_feed({"title": "New Title", "max_items": 5})
    assert result.status == "updated"
    assert service.get_feed()["config"]["title"] == "New Title"


def test_list_entries_filters_by_lifecycle(service):
    service.create_entry({"id": "urn:uuid:l1", "title": "A", "summary": "x"})
    service.create_entry({"id": "urn:uuid:l2", "title": "B", "summary": "x"})
    service.unpublish_entry("urn:uuid:l2")
    assert len(service.list_entries(lifecycle="archived")) == 1
    assert len(service.list_entries()) == 2


def test_get_entry_missing_returns_none(service):
    assert service.get_entry("urn:uuid:nope") is None


def test_get_asset_missing_returns_none(service):
    assert service.get_asset("asset:sha256:nope") is None


def test_unknown_asset_reference_rejected_before_commit(service):
    with pytest.raises(ValueError, match="unknown asset"):
        service.create_entry({
            "id": "urn:uuid:badasset", "title": "Bad", "summary": "x",
            "hero_image": {"asset_id": "asset:sha256:missing"},
        })
    # State must remain renderable.
    assert service.validate_feed()["valid"] is True


def test_unknown_enclosure_asset_rejected(service):
    with pytest.raises(ValueError, match="unknown asset"):
        service.create_entry({
            "id": "urn:uuid:badencl", "title": "Bad", "summary": "x",
            "primary_enclosure": {"asset_id": "asset:sha256:missing", "mime_type": "audio/mpeg", "size_bytes": 1},
        })


def test_validate_feed_reports_missing_file(service):
    (service.settings.public_dir / "feed.xml").unlink()
    result = service.validate_feed()
    assert result["valid"] is False
    assert any("missing" in i for i in result["issues"])


def test_validate_feed_reports_invalid_xml(service):
    (service.settings.public_dir / "feed.xml").write_text("<not-rss>")
    result = service.validate_feed()
    assert result["valid"] is False


def test_audit_warns_on_future_publication_and_missing_alt(service):
    service.create_entry({
        "id": "urn:uuid:audit", "title": "Future", "summary": "x",
        "published_at": "2999-01-01T00:00:00Z",
        "hero_image": {"url": "https://cdn.example/i.png"},
    })
    warnings = service.audit_feed()["warnings"]
    assert any("future" in w for w in warnings)
    assert any("alt text" in w for w in warnings)


def test_export_state_shape(service):
    service.create_entry({"id": "urn:uuid:exp", "title": "A", "summary": "x"})
    state = service.export_state()
    assert state["schema_version"] == 1
    assert len(state["entries"]) == 1
    assert state["feed"]["title"]


def test_rebuild_recovers_public_tree_from_sqlite(service):
    service.create_entry({"id": "urn:uuid:recover", "title": "Recover", "summary": "x"})
    import shutil
    shutil.rmtree(service.settings.public_dir)
    service.settings.public_dir.mkdir(parents=True, exist_ok=True)
    service.rebuild_public()
    assert (service.settings.public_dir / "feed.xml").exists()
    assert service.validate_feed()["valid"] is True


def test_batch_upsert_creates_then_updates(service):
    result = service.publish_batch([
        {"operation": "upsert", "entry": {"id": "urn:uuid:ups", "title": "A", "summary": "x"}},
    ])
    assert result["results"][0]["status"] == "created"
    result2 = service.publish_batch([
        {"operation": "upsert", "id": "urn:uuid:ups", "patch": {"summary": "y"}},
    ])
    assert result2["results"][0]["status"] == "updated"


def test_batch_update_missing_raises(service):
    with pytest.raises(KeyError):
        service.publish_batch([{"operation": "update", "id": "urn:uuid:none", "patch": {"summary": "x"}}])


def test_batch_archived_target_is_reported(service):
    service.create_entry({"id": "urn:uuid:arch", "title": "A", "summary": "x"})
    service.unpublish_entry("urn:uuid:arch")
    result = service.publish_batch([{"operation": "update", "id": "urn:uuid:arch", "patch": {"summary": "y"}}])
    assert result["results"][0]["status"] == "archived_target"


def test_batch_unsupported_operation_raises(service):
    with pytest.raises(ValueError, match="unsupported batch operation"):
        service.publish_batch([{"operation": "delete", "id": "urn:uuid:x"}])


def test_batch_all_noops_returns_unchanged(service):
    service.create_entry({"id": "urn:uuid:noop", "title": "A", "summary": "x"})
    result = service.publish_batch([{"operation": "update", "id": "urn:uuid:noop", "patch": {"title": "A", "summary": "x"}}])
    assert result["status"] == "unchanged"


def test_add_asset_deduplicates_via_service(service, tmp_path):
    image = tmp_path / "dup.png"
    Image.new("RGB", (6, 6)).save(image)
    first = service.add_asset(image, "dup.png", "image/png")
    second = service.add_asset(image, "dup.png", "image/png")
    assert first["asset_id"] == second["asset_id"]
    assert service.get_asset(first["asset_id"])["public_url"].startswith("https://rss.example.test/media/")


def test_validate_entry_urls_rejects_bad_scheme(service):
    with pytest.raises(ValueError, match="unsupported URL scheme"):
        service.create_entry({"id": "urn:uuid:badurl", "title": "A", "summary": "x", "url": "ftp://x/y"})


def test_media_url_relative_is_normalized(service):
    created = service.create_entry({
        "id": "urn:uuid:relmedia", "title": "A", "summary": "x",
        "media": [{"url": "pic.png", "mime_type": "image/png"}],
    })
    xml = (service.settings.public_dir / "feed.xml").read_text()
    assert "https://rss.example.test/media/pic.png" in xml


def test_batch_create_without_id_generates_uuid(service):
    result = service.publish_batch([{"operation": "create", "entry": {"title": "Auto", "summary": "x"}}])
    assert result["results"][0]["id"].startswith("urn:uuid:")


def test_batch_upsert_without_id_generates_uuid(service):
    result = service.publish_batch([{"operation": "upsert", "entry": {"title": "Auto", "summary": "x"}}])
    assert result["results"][0]["status"] == "created"
    assert result["results"][0]["id"].startswith("urn:uuid:")


def test_validate_feed_reports_non_rss_root(service):
    (service.settings.public_dir / "feed.xml").write_text("<feed><channel/></feed>")
    result = service.validate_feed()
    assert result["valid"] is False
    assert any("root element is not rss" in i for i in result["issues"])


def test_validate_feed_reports_missing_channel(service):
    (service.settings.public_dir / "feed.xml").write_text("<rss version='2.0'></rss>")
    result = service.validate_feed()
    assert any("channel missing" in i for i in result["issues"])


def test_validate_feed_reports_item_problems(service):
    (service.settings.public_dir / "feed.xml").write_text(
        "<rss version='2.0'><channel><title>t</title><link>l</link><description>d</description>"
        "<item><guid>dup</guid><title>a</title></item>"
        "<item><guid>dup</guid><title>b</title></item>"
        "<item><title>no guid</title></item>"
        "<item><guid>empty</guid></item>"
        "</channel></rss>"
    )
    issues = service.validate_feed()["issues"]
    assert any("duplicate guid" in i for i in issues)
    assert any("item missing guid" in i for i in issues)
    assert any("lacks title and description" in i for i in issues)


def test_audit_warns_on_private_media_url(service):
    service.create_entry({
        "id": "urn:uuid:privmedia", "title": "A", "summary": "x",
        "media": [{"url": "http://192.168.1.5/pic.png", "mime_type": "image/png"}],
    })
    warnings = service.audit_feed()["warnings"]
    assert any("media URL appears local/private" in w for w in warnings)


def test_configure_feed_archives_overflow(service):
    for i in range(3):
        service.create_entry({"id": f"urn:uuid:ov{i}", "title": f"E{i}", "summary": "x", "published_at": f"2026-09-2{i}T00:00:00Z"})
    service.configure_feed({"max_items": 1})
    assert len(service.list_active_entries()["entries"]) == 1
    assert len(service.list_entries(lifecycle="archived")) == 2

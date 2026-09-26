from datetime import datetime, timezone
import pytest


def base_entry(**extra):
    data = {
        "id": "urn:uuid:11111111-1111-1111-1111-111111111111",
        "kind": "status",
        "title": "Omega is testing",
        "summary": "Integration tests are running.",
        "published_at": "2026-09-26T12:00:00Z",
        "continuity_key": "agent:omega:status",
    }
    data.update(extra)
    return data


def test_create_assigns_stable_permalink(service):
    result = service.create_entry(base_entry())
    assert result.status == "created"
    entry = service.get_entry(result.id)
    assert entry["private_metadata"]["local_permalink_path"].startswith("/entries/")
    assert service.validate_feed()["valid"] is True


def test_update_preserves_guid_and_original_pubdate(service):
    service.create_entry(base_entry())
    result = service.update_entry(base_entry()["id"], {"title": "Omega reaches RC", "summary": "201 tests pass."})
    assert result.status == "updated"
    entry = service.get_entry(base_entry()["id"])
    assert entry["id"] == base_entry()["id"]
    assert entry["published_at"].startswith("2026-09-26T12:00:00")
    assert entry["title"] == "Omega reaches RC"


def test_guid_mutation_is_rejected(service):
    service.create_entry(base_entry())
    with pytest.raises(ValueError, match="immutable"):
        service.update_entry(base_entry()["id"], {"id": "urn:uuid:different"})


def test_identical_update_is_noop(service):
    first = service.create_entry(base_entry())
    before = service.get_feed()["revision"]
    entry_before = service.get_entry(first.id)
    result = service.update_entry(first.id, {"title": entry_before["title"], "summary": entry_before["summary"]})
    assert result.status == "unchanged"
    assert service.get_feed()["revision"] == before
    assert service.get_entry(first.id)["updated_at"] == entry_before["updated_at"]


def test_unpublish_requires_explicit_republish(service):
    entry_id = base_entry()["id"]
    service.create_entry(base_entry())
    assert service.unpublish_entry(entry_id).status == "unpublished"
    assert service.update_entry(entry_id, {"summary": "new"}).status == "archived_target"
    assert service.republish_entry(entry_id).status == "republished"
    assert service.get_entry(entry_id)["lifecycle"] == "published"


def test_retraction_keeps_identity(service):
    entry_id = base_entry()["id"]
    service.create_entry(base_entry())
    result = service.retract_entry(entry_id, "The original status was incorrect.")
    assert result.status == "retracted"
    entry = service.get_entry(entry_id)
    assert entry["id"] == entry_id
    assert entry["lifecycle"] == "retracted"

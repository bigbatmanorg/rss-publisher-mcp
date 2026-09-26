import pytest
from rss_publisher.service import RevisionConflict


def test_expected_revision_detects_stale_writer(service):
    rev = service.get_feed()["revision"]
    service.create_entry({"title": "A", "summary": "x"}, expected_revision=rev)
    with pytest.raises(RevisionConflict):
        service.create_entry({"title": "B", "summary": "x"}, expected_revision=rev)


def test_batch_rebuilds_and_handles_noops(service):
    result = service.publish_batch([
        {"operation": "create", "entry": {"id": "urn:uuid:99999999-9999-9999-9999-999999999999", "title": "One", "summary": "x"}},
        {"operation": "create", "entry": {"id": "urn:uuid:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "title": "Two", "summary": "y"}},
    ])
    assert result["status"] == "changed"
    rev = result["feed_revision"]
    result2 = service.publish_batch([
        {"operation": "update", "id": "urn:uuid:99999999-9999-9999-9999-999999999999", "patch": {"title": "One", "summary": "x"}},
    ], expected_revision=rev)
    assert result2["status"] == "unchanged"

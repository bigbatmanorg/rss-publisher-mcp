
def test_only_retained_entries_are_active(service):
    service.configure_feed({"max_items": 2})
    for i in range(3):
        service.create_entry({
            "id": f"urn:uuid:00000000-0000-0000-0000-00000000000{i}",
            "title": f"Entry {i}",
            "summary": "x",
            "published_at": f"2026-09-2{4+i}T12:00:00Z",
        })
    active = service.list_active_entries()["entries"]
    assert len(active) == 2
    assert [x["title"] for x in active] == ["Entry 2", "Entry 1"]
    assert len(service.list_entries()) == 3


def test_retention_marks_overflow_archived(service):
    service.configure_feed({"max_items": 1})
    first = service.create_entry({"id": "urn:uuid:cccccccc-cccc-cccc-cccc-cccccccccccc", "title": "Old", "summary": "x", "published_at": "2026-09-25T10:00:00Z"})
    service.create_entry({"id": "urn:uuid:dddddddd-dddd-dddd-dddd-dddddddddddd", "title": "New", "summary": "x", "published_at": "2026-09-26T10:00:00Z"})
    assert service.get_entry(first.id)["lifecycle"] == "archived"
    assert service.update_entry(first.id, {"summary": "late change"}).status == "archived_target"

"""FreshRSS/SimplePie compatibility proxy.

FreshRSS consumes RSS via SimplePie. We cannot run the PHP stack here, so this
test models a subscriber's view by parsing the emitted feed exactly as a reader
would and asserting the interoperability behaviors the release gate requires:
create, update-under-same-GUID, no-op, media, and retention.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from PIL import Image

NS = {
    "content": "http://purl.org/rss/1.0/modules/content/",
    "media": "http://search.yahoo.com/mrss/",
    "dc": "http://purl.org/dc/elements/1.1/",
}


def _read_feed(service):
    root = ET.fromstring((service.settings.public_dir / "feed.xml").read_bytes())
    channel = root.find("channel")
    items = []
    for item in channel.findall("item"):
        items.append({
            "guid": item.findtext("guid"),
            "title": item.findtext("title"),
            "link": item.findtext("link"),
            "description": item.findtext("description"),
            "content": item.findtext("content:encoded", namespaces=NS),
            "media": [m.attrib for m in item.findall("media:content", NS)],
            "creator": item.findtext("dc:creator", namespaces=NS),
        })
    return items


def test_freshrss_create_update_noop_media_retention(service, tmp_path):
    image = tmp_path / "hero.png"
    Image.new("RGB", (64, 32)).save(image)
    asset = service.add_asset(image, "hero.png", "image/png")

    # create
    created = service.create_entry({
        "id": "urn:uuid:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "kind": "article",
        "title": "First version",
        "summary": "Initial summary",
        "content_html": "<p>Body</p>",
        "published_at": "2026-09-26T09:00:00Z",
        "authors": [{"name": "Desk"}],
        "hero_image": {"asset_id": asset["id"], "alt": "Hero"},
    })
    items = _read_feed(service)
    assert len(items) == 1
    assert items[0]["guid"] == created.id
    assert items[0]["creator"] == "Desk"
    assert items[0]["media"], "media:content must be present for readers"
    assert items[0]["media"][0]["medium"] == "image"

    # update under the same GUID
    service.update_entry(created.id, {"title": "Second version", "summary": "Updated summary"})
    items = _read_feed(service)
    assert len(items) == 1
    assert items[0]["guid"] == created.id
    assert items[0]["title"] == "Second version"

    # no-op leaves the feed byte-identical
    before = (service.settings.public_dir / "feed.xml").read_bytes()
    result = service.update_entry(created.id, {"title": "Second version", "summary": "Updated summary"})
    assert result.status == "unchanged"
    assert (service.settings.public_dir / "feed.xml").read_bytes() == before

    # retention removes the entry from the reader's view but preserves state
    service.configure_feed({"max_items": 1})
    service.create_entry({
        "id": "urn:uuid:ffffffff-0000-1111-2222-333333333333",
        "title": "Newer",
        "summary": "Newer entry",
        "published_at": "2026-09-27T09:00:00Z",
    })
    items = _read_feed(service)
    assert [i["guid"] for i in items] == ["urn:uuid:ffffffff-0000-1111-2222-333333333333"]
    assert service.get_entry(created.id)["lifecycle"] == "archived"

from rss_publisher.config import Settings
from rss_publisher.service import PublisherService


def test_canonical_state_can_render_under_new_public_base(tmp_path):
    data = tmp_path / "data"
    first = Settings(data_dir=data, public_dir=tmp_path/"public1", public_base_url="https://rss.lab.amvc.me")
    s1 = PublisherService(first)
    s1.create_entry({"id": "urn:uuid:eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee", "title": "Portable", "summary": "x"})
    second = Settings(data_dir=data, public_dir=tmp_path/"public2", public_base_url="https://rss.amvc.me")
    s2 = PublisherService(second)
    s2.rebuild_public()
    xml = (second.public_dir / "feed.xml").read_text()
    assert "https://rss.amvc.me/feed.xml" in xml
    assert "https://rss.lab.amvc.me" not in xml

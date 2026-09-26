from rss_publisher.config import Settings
from rss_publisher.service import PublisherService


def test_private_public_base_warns_for_freshrss(tmp_path):
    settings = Settings(data_dir=tmp_path/"d", public_dir=tmp_path/"p", public_base_url="http://192.168.1.20:8080")
    service = PublisherService(settings)
    service.create_entry({"title": "Lab", "summary": "x"})
    warnings = service.audit_feed()["warnings"]
    assert any("FreshRSS 1.30" in x for x in warnings)

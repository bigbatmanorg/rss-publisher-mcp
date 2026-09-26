import pytest

from rss_publisher.config import Settings, _bool, _path
from rss_publisher.urls import is_privateish_url, normalize_url


def test_relative_urls_use_public_base(settings):
    assert normalize_url(settings, "/media/x.webp") == "https://rss.example.test/media/x.webp"
    assert normalize_url(settings, "x.webp", base_path=settings.media_path) == "https://rss.example.test/media/x.webp"


def test_external_urls_are_preserved(settings):
    url = "https://example.com/a?q=1"
    assert normalize_url(settings, url) == url


def test_from_env_requires_absolute_http_base(monkeypatch):
    monkeypatch.setenv("RSS_PUBLIC_BASE_URL", "ftp://example.com")
    with pytest.raises(ValueError, match="absolute http"):
        Settings.from_env()


def test_from_env_rejects_unknown_auth_mode(monkeypatch):
    monkeypatch.setenv("RSS_PUBLIC_BASE_URL", "https://rss.example.test")
    monkeypatch.setenv("RSS_AUTH_MODE", "basic")
    with pytest.raises(ValueError, match="RSS_AUTH_MODE"):
        Settings.from_env()


def test_from_env_requires_token_for_bearer(monkeypatch):
    monkeypatch.setenv("RSS_PUBLIC_BASE_URL", "https://rss.example.test")
    monkeypatch.setenv("RSS_AUTH_MODE", "bearer")
    monkeypatch.delenv("RSS_API_TOKEN", raising=False)
    with pytest.raises(ValueError, match="RSS_API_TOKEN"):
        Settings.from_env()


def test_from_env_parses_dimensions_and_paths(monkeypatch):
    monkeypatch.setenv("RSS_PUBLIC_BASE_URL", "https://rss.example.test/")
    monkeypatch.setenv("RSS_EMBEDDINGS_DIMENSIONS", "1536")
    monkeypatch.setenv("RSS_FEED_PATH", "feed.xml")
    monkeypatch.setenv("RSS_EMBEDDINGS_ENABLED", "yes")
    settings = Settings.from_env()
    assert settings.public_base_url == "https://rss.example.test"
    assert settings.embeddings_dimensions == 1536
    assert settings.feed_path == "/feed.xml"
    assert settings.embeddings_enabled is True


def test_absolute_preserves_external_and_prefixes_local(tmp_path):
    settings = Settings(data_dir=tmp_path / "d", public_dir=tmp_path / "p", public_base_url="https://rss.example.test")
    assert settings.absolute("https://other.example/x") == "https://other.example/x"
    assert settings.absolute("/media/x") == "https://rss.example.test/media/x"
    assert settings.feed_url == "https://rss.example.test/feed.xml"
    assert settings.upload_url == "https://rss.example.test/api/v1/assets"


def test_path_helper_normalizes():
    assert _path("feed.xml") == "/feed.xml"
    assert _path("/entries/") == "/entries"
    assert _path("/") == "/"


def test_bool_helper_default_and_env(monkeypatch):
    assert _bool("MISSING", True) is True
    assert _bool("MISSING", False) is False
    monkeypatch.setenv("X_FLAG", "on")
    assert _bool("X_FLAG", False) is True
    monkeypatch.setenv("X_FLAG", "0")
    assert _bool("X_FLAG", True) is False


def test_normalize_url_none_and_blank(settings):
    assert normalize_url(settings, None) is None
    assert normalize_url(settings, "   ") is None


def test_normalize_url_rejects_unsupported_scheme(settings):
    with pytest.raises(ValueError, match="unsupported URL scheme"):
        normalize_url(settings, "ftp://example.com/x")


def test_normalize_url_relative_with_base_path(settings):
    assert normalize_url(settings, "a/b.png", base_path="/media") == "https://rss.example.test/media/a/b.png"


def test_is_privateish_url_variants():
    assert is_privateish_url("http://localhost:8080")
    assert is_privateish_url("http://127.0.0.1")
    assert is_privateish_url("http://[::1]")
    assert is_privateish_url("http://host.local")
    assert is_privateish_url("http://10.0.0.5")
    assert is_privateish_url("http://192.168.1.1")
    assert is_privateish_url("http://172.16.0.1")
    assert not is_privateish_url("https://rss.example.test")

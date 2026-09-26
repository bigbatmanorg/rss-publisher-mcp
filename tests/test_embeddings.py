from rss_publisher.config import Settings
from rss_publisher.embeddings import EmbeddingProvider, cosine, semantic_hash, semantic_text
from rss_publisher.models import FeedEntry
from rss_publisher.service import PublisherService
import pytest


def fake_vector(text: str):
    text = text.lower()
    return [float("omega" in text), float("microsoft" in text), float("outage" in text), 1.0]


def test_embedding_search_only_uses_active_entries(tmp_path):
    settings = Settings(
        data_dir=tmp_path / "data", public_dir=tmp_path / "public",
        public_base_url="https://rss.example.test", embeddings_enabled=True,
        embeddings_model="fake", embeddings_dimensions=4,
    )
    service = PublisherService(settings, embedder=EmbeddingProvider(settings, transport=fake_vector))
    omega = service.create_entry({"id": "urn:uuid:66666666-6666-6666-6666-666666666666", "kind": "status", "title": "Omega testing", "summary": "Omega integration tests", "published_at": "2026-09-26T09:00:00Z"})
    ms = service.create_entry({"id": "urn:uuid:77777777-7777-7777-7777-777777777777", "title": "Microsoft outage", "summary": "Authentication outage", "published_at": "2026-09-26T10:00:00Z"})
    matches = service.find_similar_active_entries(text="Microsoft authentication outage resolved", limit=2)["matches"]
    assert matches[0]["id"] == ms.id
    service.unpublish_entry(ms.id)
    matches2 = service.find_similar_active_entries(text="Microsoft authentication outage resolved", limit=2)["matches"]
    assert all(x["id"] != ms.id for x in matches2)


def test_continuity_key_is_exact_signal(tmp_path):
    settings = Settings(data_dir=tmp_path/"d", public_dir=tmp_path/"p", public_base_url="https://rss.example.test")
    service = PublisherService(settings)
    service.create_entry({"id": "urn:uuid:88888888-8888-8888-8888-888888888888", "kind": "status", "continuity_key": "agent:omega:status", "title": "Omega", "summary": "working"})
    result = service.find_similar_active_entries(entry={"kind": "status", "continuity_key": "agent:omega:status", "summary": "done"})
    assert result["matches"][0]["signals"] == ["continuity_key"]
    assert result["matches"][0]["score"] == 1.0


def test_semantic_text_uses_html_when_no_text():
    entry = FeedEntry(title="T", summary="S", content_html="<p>Hello <b>world</b></p>")
    text = semantic_text(entry)
    assert "Hello" in text
    assert "world" in text
    assert "<b>" not in text


def test_semantic_text_includes_scalar_metadata_only():
    entry = FeedEntry(title="T", summary="S", public_metadata={"a": 1, "b": {"nested": 1}, "c": "x"})
    text = semantic_text(entry)
    assert '"a": 1' in text
    assert '"c": "x"' in text
    assert "nested" not in text


def test_semantic_hash_is_stable():
    assert semantic_hash("abc") == semantic_hash("abc")
    assert semantic_hash("abc") != semantic_hash("abd")


def test_cosine_edge_cases():
    assert cosine([], []) == 0.0
    assert cosine([1.0], [1.0, 2.0]) == 0.0
    assert cosine([0.0, 0.0], [1.0, 1.0]) == 0.0
    assert cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)


def test_embedding_provider_requires_configuration():
    settings = Settings(data_dir=__import__("pathlib").Path("/tmp/d"), public_dir=__import__("pathlib").Path("/tmp/p"), public_base_url="https://rss.example.test", embeddings_enabled=True)
    provider = EmbeddingProvider(settings)
    with pytest.raises(RuntimeError, match="not configured"):
        provider.embed("x")


def test_embedding_provider_disabled_raises():
    settings = Settings(data_dir=__import__("pathlib").Path("/tmp/d"), public_dir=__import__("pathlib").Path("/tmp/p"), public_base_url="https://rss.example.test", embeddings_enabled=False)
    provider = EmbeddingProvider(settings)
    with pytest.raises(RuntimeError, match="disabled"):
        provider.embed("x")


def test_embedding_provider_posts_to_endpoint(monkeypatch):
    settings = Settings(
        data_dir=__import__("pathlib").Path("/tmp/d"), public_dir=__import__("pathlib").Path("/tmp/p"),
        public_base_url="https://rss.example.test", embeddings_enabled=True,
        embeddings_base_url="https://api.example.test/v1", embeddings_model="m", embeddings_api_key="k",
        embeddings_dimensions=3,
    )
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"embedding": [0.1, 0.2, 0.3]}]}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return FakeResponse()

    import rss_publisher.embeddings as emb
    monkeypatch.setattr(emb.httpx, "post", fake_post)
    provider = EmbeddingProvider(settings)
    vector = provider.embed("hello")
    assert vector == [0.1, 0.2, 0.3]
    assert captured["url"] == "https://api.example.test/v1/embeddings"
    assert captured["json"]["dimensions"] == 3
    assert captured["headers"]["Authorization"] == "Bearer k"


def test_embedding_outage_degrades_without_corrupting_publication(tmp_path):
    settings = Settings(
        data_dir=tmp_path / "data", public_dir=tmp_path / "public",
        public_base_url="https://rss.example.test", embeddings_enabled=True,
        embeddings_model="fake", embeddings_dimensions=4,
    )

    def boom(text):
        raise RuntimeError("provider down")

    service = PublisherService(settings, embedder=EmbeddingProvider(settings, transport=boom))
    result = service.create_entry({"id": "urn:uuid:12121212-1212-1212-1212-121212121212", "title": "Still published", "summary": "x"})
    assert result.status == "created"
    assert any("embedding index degraded" in w for w in result.warnings)
    assert service.validate_feed()["valid"] is True


def test_model_change_rebuilds_active_embeddings(tmp_path):
    settings = Settings(
        data_dir=tmp_path / "data", public_dir=tmp_path / "public",
        public_base_url="https://rss.example.test", embeddings_enabled=True,
        embeddings_model="model-a", embeddings_dimensions=4,
    )
    calls = {"n": 0}

    def transport(text):
        calls["n"] += 1
        return [1.0, 0.0, 0.0, 1.0]

    service = PublisherService(settings, embedder=EmbeddingProvider(settings, transport=transport))
    service.create_entry({"id": "urn:uuid:13131313-1313-1313-1313-131313131313", "title": "A", "summary": "x"})
    first_calls = calls["n"]
    # Same model + unchanged semantic hash -> no re-embed.
    service.rebuild_public()
    service._sync_embeddings()
    assert calls["n"] == first_calls
    # Model change invalidates and re-embeds.
    service.settings = Settings(**{**settings.__dict__, "embeddings_model": "model-b"})
    service._sync_embeddings()
    assert calls["n"] > first_calls


def test_find_similar_requires_text_or_entry(service):
    with pytest.raises(ValueError, match="text or entry is required"):
        service.find_similar_active_entries()


def test_find_similar_degrades_when_disabled(service):
    service.create_entry({"id": "urn:uuid:14141414-1414-1414-1414-141414141414", "title": "A", "summary": "x"})
    result = service.find_similar_active_entries(text="anything")
    assert result["matches"] == []
    assert result["degraded"] == "embeddings_disabled"

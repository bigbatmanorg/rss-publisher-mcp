import importlib
from PIL import Image
from fastapi.testclient import TestClient


def _reload_api(tmp_path, monkeypatch, **env):
    monkeypatch.setenv("RSS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("RSS_PUBLIC_DIR", str(tmp_path / "public"))
    monkeypatch.setenv("RSS_PUBLIC_BASE_URL", "https://rss.example.test")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    import rss_publisher.api as api
    return importlib.reload(api)


def test_upload_api_and_service_discovery(tmp_path, monkeypatch):
    api = _reload_api(tmp_path, monkeypatch, RSS_AUTH_MODE="none")
    client = TestClient(api.app)
    info = client.get("/api/v1/service")
    assert info.status_code == 200
    assert info.json()["publication"]["feed_url"] == "https://rss.example.test/feed.xml"
    image_path = tmp_path / "x.png"
    Image.new("RGB", (10, 10)).save(image_path)
    with image_path.open("rb") as f:
        response = client.post("/api/v1/assets", files={"file": ("x.png", f, "image/png")})
    assert response.status_code == 200
    assert response.json()["asset_id"].startswith("asset:sha256:")


def test_bearer_auth_is_optional_but_enforced_when_enabled(tmp_path, monkeypatch):
    api = _reload_api(tmp_path, monkeypatch, RSS_AUTH_MODE="bearer", RSS_API_TOKEN="secret")
    client = TestClient(api.app)
    assert client.post("/api/v1/assets").status_code == 401


def test_bearer_auth_accepts_correct_token(tmp_path, monkeypatch):
    api = _reload_api(tmp_path, monkeypatch, RSS_AUTH_MODE="bearer", RSS_API_TOKEN="secret")
    client = TestClient(api.app)
    image_path = tmp_path / "y.png"
    Image.new("RGB", (4, 4)).save(image_path)
    with image_path.open("rb") as f:
        response = client.post(
            "/api/v1/assets",
            files={"file": ("y.png", f, "image/png")},
            headers={"Authorization": "Bearer secret"},
        )
    assert response.status_code == 200
    asset_id = response.json()["asset_id"]
    meta = client.get(f"/api/v1/assets/{asset_id}", headers={"Authorization": "Bearer secret"})
    assert meta.status_code == 200
    assert meta.json()["asset_id"] == asset_id


def test_health_and_ready(tmp_path, monkeypatch):
    api = _reload_api(tmp_path, monkeypatch, RSS_AUTH_MODE="none")
    client = TestClient(api.app)
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").json() == {"status": "ready"}


def test_asset_metadata_404(tmp_path, monkeypatch):
    api = _reload_api(tmp_path, monkeypatch, RSS_AUTH_MODE="none")
    client = TestClient(api.app)
    assert client.get("/api/v1/assets/asset:sha256:missing").status_code == 404


def test_upload_rejects_active_content(tmp_path, monkeypatch):
    api = _reload_api(tmp_path, monkeypatch, RSS_AUTH_MODE="none")
    client = TestClient(api.app)
    response = client.post("/api/v1/assets", files={"file": ("bad.html", b"<script>x</script>", "text/html")})
    assert response.status_code == 400


def test_upload_rejects_oversized(tmp_path, monkeypatch):
    api = _reload_api(tmp_path, monkeypatch, RSS_AUTH_MODE="none", RSS_MAX_UPLOAD_BYTES="8")
    client = TestClient(api.app)
    response = client.post("/api/v1/assets", files={"file": ("big.bin", b"x" * 64, "application/octet-stream")})
    assert response.status_code == 413

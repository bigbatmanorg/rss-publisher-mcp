from pathlib import Path
from PIL import Image
import io
import pytest

from rss_publisher.assets import detect_type, ingest_temp_file, temp_file_from_stream


def test_image_asset_is_content_addressed_and_deduplicated(service, tmp_path):
    image = tmp_path / "hero.png"
    Image.new("RGB", (32, 20)).save(image)
    first = service.add_asset(image, "hero.png", "image/png")
    second = service.add_asset(image, "other-name.png", "image/png")
    assert first["id"] == second["id"]
    assert first["width"] == 32 and first["height"] == 20
    assert first["public_url"].startswith("https://rss.example.test/media/")
    assert Path(first["storage_path"]).exists()


def test_active_html_upload_is_rejected(service, tmp_path):
    path = tmp_path / "bad.html"
    path.write_text("<script>alert(1)</script>")
    with pytest.raises(ValueError, match="active web content"):
        service.add_asset(path, "bad.html", "text/html")


def test_active_svg_upload_is_rejected(service, tmp_path):
    path = tmp_path / "bad.svg"
    path.write_text('<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>')
    with pytest.raises(ValueError, match="active web content"):
        service.add_asset(path, "bad.svg", "image/svg+xml")


def test_active_xhtml_upload_is_rejected(service, tmp_path):
    path = tmp_path / "bad.xhtml"
    path.write_text("<html><body>x</body></html>")
    with pytest.raises(ValueError, match="active web content"):
        service.add_asset(path, "bad.xhtml", "application/xhtml+xml")


def test_hero_asset_is_rendered_as_media_and_html(service, tmp_path):
    image = tmp_path / "hero.png"
    Image.new("RGB", (8, 8)).save(image)
    asset = service.add_asset(image, "hero.png", "image/png")
    service.create_entry({
        "id": "urn:uuid:55555555-5555-5555-5555-555555555555",
        "title": "With Image", "summary": "image", "published_at": "2026-09-26T09:00:00Z",
        "hero_image": {"asset_id": asset["id"], "alt": "A test image"}
    })
    xml = (service.settings.public_dir / "feed.xml").read_text()
    assert "media:content" in xml
    assert "media:thumbnail" in xml
    assert "&lt;figure&gt;" in xml
    assert asset["public_url"] in xml


def _png(path: Path, size=(12, 7)):
    Image.new("RGB", size).save(path)
    return path


def test_detect_pdf(tmp_path):
    path = tmp_path / "doc.pdf"
    path.write_bytes(b"%PDF-1.7\n...")
    mime, w, h, ext = detect_type(path)
    assert mime == "application/pdf"
    assert ext == "pdf"
    assert w is None and h is None


def test_detect_webp(tmp_path):
    path = tmp_path / "img.webp"
    Image.new("RGB", (5, 5)).save(path, format="WEBP")
    mime, w, h, ext = detect_type(path)
    assert mime == "image/webp"
    assert (w, h) == (5, 5)
    assert ext == "webp"


def test_detect_mp4_by_ftyp(tmp_path):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 16)
    mime, _, _, ext = detect_type(path)
    assert mime == "video/mp4"
    assert ext == "mp4"


def test_detect_mp3_by_id3(tmp_path):
    path = tmp_path / "audio.mp3"
    path.write_bytes(b"ID3\x04\x00\x00" + b"\x00" * 16)
    mime, _, _, ext = detect_type(path)
    assert mime == "audio/mpeg"
    assert ext == "mp3"


def test_detect_mp3_by_frame_sync(tmp_path):
    path = tmp_path / "audio2.mp3"
    path.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 16)
    mime, _, _, ext = detect_type(path)
    assert mime == "audio/mpeg"


def test_detect_active_content_flagged(tmp_path):
    path = tmp_path / "page.html"
    path.write_bytes(b"<html></html>")
    mime, _, _, _ = detect_type(path, "text/html")
    assert mime == "text/html"


def test_detect_supplied_application_types(tmp_path):
    path = tmp_path / "data.json"
    path.write_bytes(b'{"a":1}')
    mime, _, _, ext = detect_type(path, "application/json")
    assert mime == "application/json"
    assert ext == "json"


def test_detect_unknown_falls_back_to_octet_stream(tmp_path):
    path = tmp_path / "blob.bin"
    path.write_bytes(b"\x00\x01\x02\x03" * 4)
    mime, _, _, ext = detect_type(path)
    assert mime == "application/octet-stream"
    assert ext == "bin"


def test_ingest_rejects_oversized(settings, tmp_path):
    path = tmp_path / "big.bin"
    path.write_bytes(b"x" * 32)
    small = settings.__class__(**{**settings.__dict__, "max_upload_bytes": 8})
    with pytest.raises(ValueError, match="max upload size"):
        ingest_temp_file(small, path, "big.bin", None)


def test_ingest_pdf_goes_to_files_bucket(settings, tmp_path):
    path = tmp_path / "doc.pdf"
    path.write_bytes(b"%PDF-1.7\ncontent")
    meta = ingest_temp_file(settings, path, "doc.pdf", "application/pdf")
    assert meta["public_path"].startswith("/files/")
    assert meta["id"].startswith("asset:sha256:")
    assert Path(meta["storage_path"]).exists()


def test_ingest_is_idempotent_on_disk(settings, tmp_path):
    path = _png(tmp_path / "a.png")
    first = ingest_temp_file(settings, path, "a.png", "image/png")
    second = ingest_temp_file(settings, path, "a.png", "image/png")
    assert first["storage_path"] == second["storage_path"]


def test_temp_file_from_stream_roundtrip():
    path = temp_file_from_stream(io.BytesIO(b"hello world"), max_bytes=100)
    try:
        assert path.read_bytes() == b"hello world"
    finally:
        path.unlink(missing_ok=True)


def test_temp_file_from_stream_enforces_limit():
    with pytest.raises(ValueError, match="max upload size"):
        temp_file_from_stream(io.BytesIO(b"x" * 50), max_bytes=10)

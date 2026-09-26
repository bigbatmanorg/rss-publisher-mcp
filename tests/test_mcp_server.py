from __future__ import annotations

import importlib
import sys

import pytest


def _load_server(monkeypatch, tmp_path, **env):
    monkeypatch.setenv("RSS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("RSS_PUBLIC_DIR", str(tmp_path / "public"))
    monkeypatch.setenv("RSS_PUBLIC_BASE_URL", "https://rss.example.test")
    monkeypatch.setenv("RSS_EMBEDDINGS_ENABLED", "false")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    sys.modules.pop("rss_publisher.mcp_server", None)
    return importlib.import_module("rss_publisher.mcp_server")


def test_service_resource_reports_configuration(monkeypatch, tmp_path):
    server = _load_server(monkeypatch, tmp_path)
    import json
    payload = json.loads(server.service_resource())
    assert payload["public_base_url"] == "https://rss.example.test"
    assert payload["feed_url"] == "https://rss.example.test/feed.xml"
    assert payload["auth_mode"] == "none"


def test_main_stdio_transport(monkeypatch, tmp_path):
    server = _load_server(monkeypatch, tmp_path, RSS_MCP_TRANSPORT="stdio")
    calls = {}
    monkeypatch.setattr(server.mcp, "run", lambda **kwargs: calls.update(kwargs))
    server.main()
    assert calls == {"transport": "stdio"}


def test_main_streamable_http_transport(monkeypatch, tmp_path):
    server = _load_server(
        monkeypatch, tmp_path,
        RSS_MCP_TRANSPORT="streamable-http",
        RSS_MCP_LISTEN_HOST="127.0.0.1",
        RSS_MCP_LISTEN_PORT="9999",
    )
    calls = {}
    monkeypatch.setattr(server.mcp, "run", lambda **kwargs: calls.update(kwargs))
    server.main()
    assert calls["transport"] == "streamable-http"
    assert calls["host"] == "127.0.0.1"
    assert calls["port"] == 9999
    assert calls["streamable_http_path"] == "/mcp"


def test_main_http_alias_transport(monkeypatch, tmp_path):
    server = _load_server(monkeypatch, tmp_path, RSS_MCP_TRANSPORT="http")
    calls = {}
    monkeypatch.setattr(server.mcp, "run", lambda **kwargs: calls.update(kwargs))
    server.main()
    assert calls["transport"] == "streamable-http"


def test_main_rejects_unknown_transport(monkeypatch, tmp_path):
    server = _load_server(monkeypatch, tmp_path, RSS_MCP_TRANSPORT="carrier-pigeon")
    with pytest.raises(SystemExit):
        server.main()


def test_tool_functions_delegate_to_service(monkeypatch, tmp_path):
    server = _load_server(monkeypatch, tmp_path)
    created = server.create_entry({"title": "Via MCP", "summary": "x"})
    assert created["id"].startswith("urn:uuid:")
    assert server.get_entry(created["id"])["title"] == "Via MCP"
    assert server.list_active_entries()["entries"]
    assert server.get_feed()["config"]["title"]
    assert server.validate_feed()["valid"] is True
    assert server.audit_feed()["ok"] is True
    assert server.rebuild_feed()["valid"] is True
    assert server.get_asset("asset:sha256:nope") is None
    assert server.find_similar_active_entries(text="anything")["matches"] == []

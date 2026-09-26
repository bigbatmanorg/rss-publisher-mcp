import asyncio
import importlib
import sys

import pytest


def test_current_mcp_sdk_lists_expected_tools(monkeypatch, tmp_path):
    pytest.importorskip("mcp")
    from mcp import Client

    monkeypatch.setenv("RSS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("RSS_PUBLIC_DIR", str(tmp_path / "public"))
    monkeypatch.setenv("RSS_PUBLIC_BASE_URL", "https://rss.example.test")
    monkeypatch.setenv("RSS_EMBEDDINGS_ENABLED", "false")
    sys.modules.pop("rss_publisher.mcp_server", None)
    server = importlib.import_module("rss_publisher.mcp_server")

    async def check():
        async with Client(server.mcp, raise_exceptions=True) as client:
            result = await client.list_tools()
            names = {t.name for t in result.tools}
            expected = {
                "get_feed", "configure_feed", "list_active_entries",
                "find_similar_active_entries", "get_entry", "create_entry",
                "update_entry", "publish_batch", "correct_entry",
                "retract_entry", "unpublish_entry", "republish_entry",
                "get_asset", "validate_feed", "audit_feed", "rebuild_feed",
            }
            assert expected <= names
            called = await client.call_tool("get_feed", {})
            assert not called.is_error

    asyncio.run(check())

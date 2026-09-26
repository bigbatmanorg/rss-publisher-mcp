from __future__ import annotations

import json
import os
from typing import Any
from mcp.server import MCPServer

from .config import Settings
from .models import FeedEntry
from .service import PublisherService
from . import __version__

settings = Settings.from_env()
service = PublisherService(settings)
mcp = MCPServer(
    "rss-publisher",
    title="RSS Publisher",
    version=__version__,
    instructions=(
        "Deterministic RSS publishing backend. Maintain stable entry IDs, use active semantic search only for candidates, "
        "and never treat unpublishing as deletion from subscribers. Public deployment base: " + settings.public_base_url +
        ". Binary assets are uploaded via " + settings.upload_url
    ),
)


@mcp.tool()
def get_feed() -> dict[str, Any]:
    """Return feed configuration, current revision, and publication URL."""
    return service.get_feed()


@mcp.tool()
def configure_feed(patch: dict[str, Any], expected_revision: int | None = None) -> dict[str, Any]:
    """Update feed/channel configuration."""
    return service.configure_feed(patch, expected_revision).model_dump(mode="json")


@mcp.tool()
def list_active_entries() -> dict[str, Any]:
    """Return compact summaries of entries currently emitted into feed.xml."""
    return service.list_active_entries()


@mcp.tool()
def find_similar_active_entries(text: str | None = None, entry: dict[str, Any] | None = None, limit: int = 5) -> dict[str, Any]:
    """Find semantic candidates only among currently active/published entries. Similarity is candidate retrieval, not authority to merge."""
    return service.find_similar_active_entries(text=text, entry=entry, limit=limit)


@mcp.tool()
def get_entry(entry_id: str) -> dict[str, Any] | None:
    """Return the complete canonical FeedEntry by immutable ID."""
    return service.get_entry(entry_id)


@mcp.tool()
def create_entry(entry: dict[str, Any], expected_revision: int | None = None) -> dict[str, Any]:
    """Create a definitely-new entry. Generates a permanent urn:uuid ID if omitted."""
    return service.create_entry(entry, expected_revision).model_dump(mode="json")


@mcp.tool()
def update_entry(entry_id: str, patch: dict[str, Any], expected_revision: int | None = None) -> dict[str, Any]:
    """Patch an active entry while preserving its immutable ID. Archived entries require republish_entry first."""
    return service.update_entry(entry_id, patch, expected_revision).model_dump(mode="json")


@mcp.tool()
def publish_batch(operations: list[dict[str, Any]], expected_revision: int | None = None) -> dict[str, Any]:
    """Apply multiple creates/updates in one publisher transaction and rebuild once."""
    return service.publish_batch(operations, expected_revision)


@mcp.tool()
def correct_entry(entry_id: str, correction_note: str, patch: dict[str, Any] | None = None) -> dict[str, Any]:
    """Publish a visible correction while preserving entry identity."""
    return service.correct_entry(entry_id, correction_note, patch).model_dump(mode="json")


@mcp.tool()
def retract_entry(entry_id: str, reason: str | None = None) -> dict[str, Any]:
    """Publish an explicit retraction under the same immutable entry ID."""
    return service.retract_entry(entry_id, reason).model_dump(mode="json")


@mcp.tool()
def unpublish_entry(entry_id: str) -> dict[str, Any]:
    """Stop emitting an entry. This does not delete copies already stored by RSS subscribers."""
    return service.unpublish_entry(entry_id).model_dump(mode="json")


@mcp.tool()
def republish_entry(entry_id: str) -> dict[str, Any]:
    """Explicitly revive an archived/unpublished entry into the active feed."""
    return service.republish_entry(entry_id).model_dump(mode="json")


@mcp.tool()
def get_asset(asset_id: str) -> dict[str, Any] | None:
    """Return metadata/public URL for an already-uploaded asset. Binary upload itself is performed over the HTTP asset API."""
    return service.get_asset(asset_id)


@mcp.tool()
def validate_feed() -> dict[str, Any]:
    """Strict local RSS/XML validation."""
    return service.validate_feed()


@mcp.tool()
def audit_feed() -> dict[str, Any]:
    """Return interoperability warnings, including private URL/FreshRSS gotchas."""
    return service.audit_feed()


@mcp.tool()
def rebuild_feed() -> dict[str, Any]:
    """Regenerate deterministic public artifacts from authoritative SQLite state."""
    service.rebuild_public()
    return service.validate_feed()


@mcp.resource("rss-publisher://service")
def service_resource() -> str:
    return json.dumps({
        "public_base_url": settings.public_base_url,
        "feed_url": settings.feed_url,
        "upload_url": settings.upload_url,
        "auth_mode": settings.auth_mode,
    }, indent=2)


def main() -> None:
    transport = os.getenv("RSS_MCP_TRANSPORT", "stdio")
    if transport == "stdio":
        mcp.run(transport="stdio")
    elif transport in {"streamable-http", "http"}:
        host = os.getenv("RSS_MCP_LISTEN_HOST", "127.0.0.1")
        port = int(os.getenv("RSS_MCP_LISTEN_PORT", "8766"))
        mcp.run(transport="streamable-http", host=host, port=port, streamable_http_path="/mcp", stateless_http=True, json_response=True)
    else:
        raise SystemExit(f"unsupported RSS_MCP_TRANSPORT={transport}")

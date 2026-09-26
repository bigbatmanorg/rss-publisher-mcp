# rss-publisher-mcp

Deterministic, generic RSS publishing engine for `bigbatmanorg/rss-publisher-agent` and other MCP/Python/CLI clients.

Repository target: `https://github.com/bigbatmanorg/rss-publisher-mcp`

## What it owns

- Generic `FeedEntry` model (article, note, status, release, incident, media, etc.)
- Immutable RSS GUIDs and explicit lifecycle (`published`, `corrected`, `retracted`, `archived`)
- SQLite canonical state
- Deterministic RSS 2.0 rendering with Content Module, Media RSS, Dublin Core, Atom and optional `rp:*` metadata
- Stable local permalinks and public URL normalization from `RSS_PUBLIC_BASE_URL`
- Publisher-owned content-addressed media/file assets
- Optional OpenAI-compatible embeddings for candidate retrieval among **currently active** feed entries only
- Strict no-op detection
- Atomic static output writes and rebuild/recovery from SQLite
- MCP tools, Python API, CLI, and a small HTTP upload/discovery API

It does **not** do research, editorial reasoning, Docker Agent orchestration, A2A, OpenAI chat serving, Caddy, or external authentication workflows. Those belong to `rss-publisher-agent`.

## Install

```bash
uv tool install git+https://github.com/bigbatmanorg/rss-publisher-mcp.git
```

During development:

```bash
uv sync --extra dev
uv run pytest
```

## Run MCP over stdio

```bash
cp .env.example .env
set -a; . ./.env; set +a
uv run rss-publisher-mcp
```

For the all-in-one appliance the same package runs a private loopback Streamable HTTP MCP:

```bash
RSS_MCP_TRANSPORT=streamable-http uv run rss-publisher-mcp
```

Default loopback endpoint: `http://127.0.0.1:8766/mcp`.

## Asset API

```bash
uv run rss-publisher-api
```

Upload:

```bash
curl -F 'file=@picture.webp' http://127.0.0.1:8765/api/v1/assets
```

Response includes a stable content-addressed `asset_id` and the public URL derived from `RSS_PUBLIC_BASE_URL`.

## Core behavior

### Stable identity

A new entry gets `urn:uuid:<uuid>` when no ID is supplied. Once created, the ID cannot be changed.

### Update vs archive

`update_entry` refuses to revive an archived entry. Revival is explicit via `republish_entry`.

### No-op

Submitting the same semantic state does not change `updated_at`, feed revision, feed XML, embedding, or public file mtime.

### Retention and semantic search

`FeedConfig.max_items` defines the active RSS window. Only those emitted entries are kept in the active embedding index and returned by fuzzy matching. Historical state remains in SQLite so GUIDs are never reused.

### Embeddings

Embeddings retrieve candidates; they never automatically merge entries. Exact GUIDs and continuity keys are authoritative. The agent decides whether a fuzzy candidate is actually the same continuing item.

## CLI

```bash
rss-publisher validate
rss-publisher audit
rss-publisher rebuild
rss-publisher export-state --output state.json
```

## Tests

The suite covers:

- immutable GUIDs
- create/update/no-op behavior
- explicit archive/republish/retraction
- deterministic byte-identical rendering
- retention/active index semantics
- content sanitization
- RSS namespace mappings
- content-addressed asset upload and deduplication
- rejection of active HTML assets
- optional semantic matching with a fake embedding provider
- optimistic revision conflicts
- optional bearer auth on the upload API
- FreshRSS private-network compatibility warnings

Run:

```bash
uv run pytest --cov=rss_publisher --cov-report=term-missing
```

## Data layout

```text
/data/publisher.db        authoritative state
/srv/public/feed.xml      generated RSS
/srv/public/index.html    generated landing page
/srv/public/entries/*     generated permalinks
/srv/public/media/*       content-addressed media
/srv/public/files/*       content-addressed generic files
```

The public tree is a projection. It can be rebuilt from SQLite.

## Security boundaries

- Uploaded HTML/XHTML/SVG active content is rejected by default.
- Article HTML is sanitized through `nh3`.
- Public media/files are content-addressed and immutable.
- HTTP upload authentication is optional (`RSS_AUTH_MODE=none|bearer`).
- The final appliance keeps this MCP private; remote clients interact with the RSS Publisher Agent instead.

# Architecture specification

## Contract

`rss-publisher-mcp` is a deterministic publishing capability. Its output must not depend on an LLM.

### Canonical state

SQLite is authoritative. `feed.xml`, HTML pages and public asset paths are projections.

### FeedEntry

`FeedEntry` is generic. It must support sparse notes/statuses as well as full rich articles. Human-readable fields must remain sufficient without the custom `rp:*` namespace.

### Identity invariants

1. Entry `id` is immutable after creation.
2. IDs are never reused, including archived items.
3. `published_at` is original publication time unless explicitly changed.
4. `updated_at` changes only for a substantive public mutation.
5. Archived entries are not implicitly revived.
6. Unpublishing is not subscriber deletion.

### Matching invariants

Exact GUID and `continuity_key` matches are authoritative. Embeddings retrieve candidates only among entries currently emitted by retention. Similarity scores never cause an automatic merge.

### Rendering profile

- RSS 2.0 base
- `content:encoded` for full HTML
- Media RSS for images/audio/video
- max one native RSS enclosure
- Dublin Core `dc:creator` for display names
- Atom `rel=self` and `atom:updated`
- optional `rp:kind` and `rp:metadata`

### Public URLs

Publisher-owned logical paths are resolved against `RSS_PUBLIC_BASE_URL`. External absolute HTTP(S) URLs are preserved. Deployment URLs are not baked into canonical asset identity.

### Failure behavior

Failed validation must not replace the last valid feed. SQLite/public divergence is recoverable by `rebuild`.

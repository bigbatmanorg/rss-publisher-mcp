# FeedEntry semantic schema

The Pydantic model in `rss_publisher.models` is authoritative. Important fields:

- `id`: immutable RSS identity; generated as `urn:uuid:*` when omitted
- `kind`: presentation hint (`article`, `status`, `note`, `release`, ...)
- `continuity_key`: optional intentional stream identity such as `agent:omega:status`
- `lifecycle`: `draft|published|corrected|retracted|archived`
- `title`, `summary`, `content_text`, `content_html`
- `url`: optional external/local target; local permalink is generated when omitted
- `published_at`, `updated_at`
- authors/categories/links
- hero image, additional media, one primary enclosure
- `public_metadata`: optionally emitted in `rp:metadata`
- `private_metadata`: never emitted

Sparse input is valid as long as the eventual non-draft entry has at least a title, summary, text or HTML content.

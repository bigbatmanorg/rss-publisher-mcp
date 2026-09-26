# Release gates

A release candidate is not ready until all required gates pass.

## Required

- [x] `uv sync --extra dev`
- [x] `pytest` passes
- [x] branch coverage target >= 90% for deterministic core (97% total)
- [x] package builds successfully (`uv build`)
- [x] `uv tool install dist/*.whl` smoke test
- [x] stdio MCP starts and exposes documented tools
- [x] loopback Streamable HTTP MCP starts at `/mcp`
- [x] HTTP asset upload works for PNG/WebP/PDF and deduplicates identical bytes
- [x] active HTML/SVG asset policy tested
- [x] fixed state renders byte-identical RSS on repeated rebuild
- [x] exact same update is a no-op
- [x] GUID mutation rejected
- [x] archived target not implicitly revived
- [x] retention removes entries from active similarity search but preserves state
- [x] embedding outage degrades semantic search without corrupting publication
- [x] model/dimension change invalidates/rebuilds active embeddings
- [x] media produces Media RSS plus HTML fallback
- [x] one native enclosure maximum enforced by schema
- [x] generated XML parses locally
- [x] generated representative feeds pass W3C Feed Validator when network integration test is enabled
- [~] optional FreshRSS integration test proves create, update-under-same-GUID, no-op, media and retention behavior
      (covered by `tests/test_freshrss_compat.py` reader-view proxy; live instance remains optional/manual)
- [x] crash/rebuild test proves public artifacts recover from SQLite

## Explicit non-goals for v1

No Atom output, JSON Feed, OPML management, FreshRSS API client, web research, PostgreSQL, external vector DB, web admin dashboard, multi-user ACLs, distributed replicas, or public deterministic MCP endpoint.

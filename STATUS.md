# Status

Finishing pass for release. Deterministic core, packaging, MCP, asset API and
rendering verified against the installed current dependencies.

## Environment

- Python 3.14.7
- `mcp` 2.2.0 (current SDK; `MCPServer` + `Client` high-level API)
- `nh3` 0.3.7
- `pydantic` 2.13.5, `fastapi` 0.141.1, `pillow` 12.3.0
- `uv` 0.12.10

## Tests run

- `pytest` (embeddings disabled): **152 passed, 1 skipped**
- `pytest` (embeddings enabled): **152 passed, 1 skipped**
- `pytest --cov=rss_publisher --cov-report=term-missing`: **97% total**, every
  deterministic-core module >= 91% (gate is >= 90%)
- `RSS_RUN_NETWORK_TESTS=1 pytest tests/test_w3c_validator.py`: **passed**
  (representative feed accepted by the W3C Feed Validator)
- `python -m compileall -q src tests`: passed
- `scripts/smoke_core.py`: `PASS core smoke`
- `uv sync --extra dev`: resolved/checked cleanly
- `uv build`: built `dist/rss_publisher_mcp-0.1.0.tar.gz` and `.whl`
- `uv tool install dist/*.whl`: installed 3 executables
  (`rss-publisher`, `rss-publisher-api`, `rss-publisher-mcp`)
- stdio MCP handshake: `initialize` + `tools/list` returned all 16 documented tools
- loopback Streamable HTTP MCP: `POST http://127.0.0.1:8799/mcp` `initialize` -> 200 OK
- asset API exercised with `RSS_AUTH_MODE=none` and `bearer` (401 without token,
  200 with token, metadata lookup with token)

The single skip is the W3C network integration test, which is opt-in via
`RSS_RUN_NETWORK_TESTS=1` (it was run and passed in this environment).

## Defects fixed

1. **`nh3` 0.3.7 API change (blocking).** `nh3.clean` now raises
   `ValueError: "rel" attribute is not allowed for tag "a" when link_rel is set`
   when `rel` is allowlisted. `sanitize_html` now passes `link_rel=None` so the
   publisher keeps managing `rel` itself (source/via/related links carry
   meaningful values). Compatibility decision documented in code.
2. **Unknown asset references were only detected at render time.** A bad
   `asset_id` on `hero_image`/`media`/`primary_enclosure` was committed to
   SQLite and then made every subsequent `rebuild_public` fail, violating the
   "failed validation must not replace the last valid feed" invariant. Added
   `_validate_asset_refs`, called from `_validate_entry_urls`, so bad references
   are rejected before commit.
3. **MCP server reported an empty version.** `MCPServer` now receives
   `title="RSS Publisher"` and `version=__version__`.

## Files changed

- `src/rss_publisher/sanitize.py` — `link_rel=None` compatibility fix
- `src/rss_publisher/service.py` — pre-commit asset-reference validation
- `src/rss_publisher/mcp_server.py` — server title/version
- `tests/test_sanitize.py` (new)
- `tests/test_config.py` (expanded)
- `tests/test_assets.py` (expanded)
- `tests/test_embeddings.py` (expanded)
- `tests/test_api.py` (expanded)
- `tests/test_cli.py` (new)
- `tests/test_models.py` (new)
- `tests/test_renderer_extra.py` (new)
- `tests/test_service_extra.py` (new)
- `tests/test_mcp_server.py` (new)
- `tests/test_main_module.py` (new)
- `tests/test_freshrss_compat.py` (new)
- `tests/test_w3c_validator.py` (new, opt-in network gate)
- `STATUS.md`, `specs/RELEASE_GATES.md`

## Invariants verified

- GUID immutability (mutation rejected; update preserves id and original pubDate)
- Archive semantics (archived target not implicitly revived; explicit republish)
- Deterministic rendering (byte-identical rebuild; identical update is a no-op)
- Active-only embedding search (retention removes entries from similarity search
  while preserving SQLite state; model/dimension change re-embeds)
- URL normalization (relative -> `RSS_PUBLIC_BASE_URL`, external preserved,
  unsupported schemes rejected)
- Asset security (HTML/XHTML/SVG active content rejected; content-addressed
  dedup; one native enclosure maximum enforced by schema)
- Embedding outage degrades semantic search without corrupting publication
- Crash/rebuild recovers the public tree from SQLite

## Compatibility decisions

- **MCP**: verified against the installed `mcp` 2.2.0 high-level `MCPServer`/
  `Client` API rather than hand-rolled wire semantics. `mcp>=2,<3` in
  `pyproject.toml` matches.
- **nh3**: `link_rel=None` is required by nh3 >= 0.3.7 when `rel` is allowlisted.
- **FreshRSS**: no PHP/SimplePie stack is available here, so the FreshRSS gate is
  covered by `tests/test_freshrss_compat.py`, which parses the emitted feed as a
  reader would and asserts create, update-under-same-GUID, no-op, media and
  retention behavior. A live FreshRSS instance remains an optional manual gate.

## Blockers

- None blocking. The only unverified-by-automation gate is a live FreshRSS
  instance (proxy-tested) and the opt-in W3C network test (run and passed here).

## Exact next action

- Optionally run the live FreshRSS integration against a real instance, then tag
  the release.

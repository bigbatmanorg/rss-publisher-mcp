# AI finishing prompt — rss-publisher-mcp

You are finishing `bigbatmanorg/rss-publisher-mcp` for release.

Treat `specs/ARCHITECTURE.md`, `specs/FEED_ENTRY_SCHEMA.md`, and `specs/RELEASE_GATES.md` as normative. Inspect the existing implementation before changing it. Do not replace deterministic behavior with prompts or LLM calls.

Your job is to:

1. Run the complete test suite and packaging checks.
2. Fix implementation defects while preserving the architectural boundaries.
3. Add missing tests before or with each fix.
4. Keep GUID immutability, archive semantics, deterministic rendering, active-only embedding search, URL normalization, and asset security as hard invariants.
5. Verify MCP against the installed current MCP Python SDK rather than implementing protocol wire semantics manually.
6. Verify representative RSS output against FreshRSS behavior and the RSS/Media RSS/Content Module assumptions described in specs.
7. Exercise both `RSS_AUTH_MODE=none` and `bearer` for the asset API.
8. Verify the package installs with `uv tool install` and exposes `rss-publisher`, `rss-publisher-api`, and `rss-publisher-mcp`.
9. Keep the deterministic package independent of Docker Agent, Caddy, A2A and OpenAI chat serving.
10. Update `STATUS.md` continuously with tests run, failures, files changed, blockers and exact next action.
11. run tests with both modes emdings enabled and disabled

Do not declare release-ready while any required release gate is unverified. If an upstream dependency changed, adapt to its real current API and document the compatibility decision.

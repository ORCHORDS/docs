# MCP Cacheable List Results

## Purpose

MCP 2026-07-28 adds explicit cache hints and deterministic ordering for list-oriented results. `tools/list`, `prompts/list`, `resources/list`, and `resources/read` can carry `ttlMs` and `cacheScope`, allowing clients to reduce unnecessary refetching without guessing how long a result is valid.

## Safe caching guidance

1. Honor `ttlMs`; absent, zero, or expired freshness should not be treated as indefinitely cacheable.
2. Respect `cacheScope` so user- or authorization-specific results are not reused across principals.
3. Preserve deterministic ordering when building indexes or cache keys.
4. Invalidate or bypass cached data after security-sensitive capability or authorization changes.
5. Keep tool invocation authorization independent from cached discovery metadata.
6. Avoid placing secrets or user-sensitive values in broadly shareable cache entries.
7. Record cache hits/misses when troubleshooting stale capability catalogs.

## Why deterministic order matters

Stable ordering reduces unnecessary cache churn and can keep higher-level prompt or model caches stable across reconnects. Clients should still treat the server's freshness and scope hints as the authority for reuse.

## Sources

- Model Context Protocol — 2026-07-28 specification release: https://blog.modelcontextprotocol.io/posts/2026-07-28/
- MCP TypeScript SDK — supporting protocol revision 2026-07-28: https://ts.sdk.modelcontextprotocol.io/v2/migration/support-2026-07-28

## Scope note

Caching is an optimization. It must not weaken authorization boundaries or become a substitute for validating an operation at execution time.

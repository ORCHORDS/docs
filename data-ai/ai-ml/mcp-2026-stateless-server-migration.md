# MCP 2026 stateless-server migration

**Issue:** Cloudflare's product MCP servers adopted the MCP 2026-07-28 specification using a fresh stateless server per request. New connections use `/mcp`; historical `/sse` URLs are aliases for Streamable HTTP and do not restore the deprecated HTTP+SSE transport.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Negotiate protocol versions and prefer Streamable HTTP/automatic transport detection.
- Keep authorization and idempotency independent of process memory; persist only necessary workflow state in an explicit durable store.
- Bound reconnection and retry, and re-discover capabilities after a version change.

## Verification

1. Connect with a 2026 client and a compatible 2025 Streamable HTTP client.
2. Restart between every request and prove correctness.
3. Force an SSE-only client and require a clear migration error rather than partial operation.

## Gotchas

A path named `/sse` does not prove SSE semantics. Stateless protocol handling does not mean tools themselves are side-effect free; mutating calls still need idempotency and authorization.

## Official sources

- https://developers.cloudflare.com/changelog/product/workers/

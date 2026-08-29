# MCP Stateless Header Routing

## Purpose

MCP 2026-07-28 makes the protocol core stateless. Streamable HTTP requests carry operation identity in `Mcp-Method` and, where applicable, `Mcp-Name`, allowing gateways, rate limiters, and authorization layers to make routing decisions without parsing the JSON-RPC body.

## Security model

Headers improve operability but do not replace request validation. Servers should verify that routing headers agree with the JSON-RPC operation and reject mismatches. Gateways should authenticate the caller and authorize the actual method/tool rather than treating a header value as proof of authority.

## Operational guidance

1. Route only on syntactically valid, expected method and tool names.
2. Apply allow-lists and rate limits before expensive downstream processing.
3. Verify header/body consistency at the server boundary.
4. Keep credentials scoped to the selected server and operation.
5. Log method/tool identity without logging bearer credentials or sensitive arguments.
6. Design any application state as explicit state rather than relying on transport-session affinity.
7. Test that requests can land on different healthy instances behind a non-sticky load balancer.

## Sources

- Model Context Protocol — 2026-07-28 specification release: https://blog.modelcontextprotocol.io/posts/2026-07-28/
- MCP TypeScript SDK — supporting protocol revision 2026-07-28: https://ts.sdk.modelcontextprotocol.io/v2/migration/support-2026-07-28

## Scope note

Header-based routing enables stateless infrastructure; it does not by itself provide authentication, authorization, or application-level idempotency.

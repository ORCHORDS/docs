# MCP Server Discovery and Version Negotiation

## Purpose

MCP 2026-07-28 removes the mandatory `initialize`/`initialized` handshake. Clients that want capability information up front can call the optional `server/discover` RPC to learn supported protocol versions, capabilities, instructions, and server metadata without creating a session.

## Guidance

1. Use discovery when capability-aware routing or version selection is needed before the first operation.
2. Treat advertised server identity metadata as informational unless separately authenticated; do not use self-reported names as authorization proof.
3. Select only a protocol version the client actually implements.
4. Fall back to legacy initialization only when backward compatibility is intentionally supported.
5. Cache discovery results only according to their freshness and scope hints.
6. Re-discover after a known server upgrade or when cached capability information expires.
7. Reject era/version mismatches rather than sending methods that do not exist in the negotiated revision.

## Sources

- Model Context Protocol — 2026-07-28 specification release: https://blog.modelcontextprotocol.io/posts/2026-07-28/
- MCP TypeScript SDK — Protocol versions: https://ts.sdk.modelcontextprotocol.io/v2/protocol-versions

## Scope note

Discovery establishes protocol compatibility and capabilities. Authentication and authorization remain separate controls.

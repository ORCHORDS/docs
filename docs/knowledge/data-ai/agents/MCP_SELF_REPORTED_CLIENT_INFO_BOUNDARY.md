# MCP Self-Reported Client Information Trust Boundary

## Purpose

The modern MCP protocol carries client identity metadata with requests, but self-reported protocol metadata is not an authentication credential. Treat it as descriptive context for display, logging, diagnostics, and compatibility—not as proof of caller identity.

## Modern MCP context

The 2026-07-28 MCP revision removed the mandatory initialize handshake and made requests self-describing. Client information can travel in request metadata, allowing any request to be routed without a protocol session.

Official SDK migration guidance explicitly treats `clientInfo` and `serverInfo` as self-reported values intended for display, logging, and debugging rather than security or behavior decisions.

## Practical controls

1. Authenticate the transport or OAuth caller independently of `clientInfo`.
2. Do not grant scopes, tenant access, administrative capability, or tool permissions because a request claims a trusted client name.
3. Treat version and product-name fields as untrusted input when rendering them in logs or user interfaces.
4. Bind authorization to validated tokens, mutually authenticated transport identity, or another explicit trust mechanism.
5. Use client metadata for diagnostics only after separating it from authoritative identity fields in logs and telemetry.
6. Avoid routing security-sensitive behavior solely from self-reported client names or versions.
7. Test spoofed and malformed metadata so authorization remains unchanged when descriptive fields are manipulated.

## Gateway implication

The modern protocol's header-based routing and self-describing requests improve stateless scaling, but observability metadata and routing hints do not become credentials merely because gateways can inspect them. Gateways should combine explicit protocol routing information with independently authenticated identity and policy.

## Sources

- Model Context Protocol — 2026-07-28 specification release: https://blog.modelcontextprotocol.io/posts/2026-07-28/
- MCP TypeScript SDK — supporting protocol revision 2026-07-28: https://ts.sdk.modelcontextprotocol.io/v2/migration/support-2026-07-28

## Scope note

This guidance concerns trust boundaries for self-reported protocol metadata. Deployments still need their own authentication, authorization, tenant isolation, and audit controls.

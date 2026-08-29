# A2A Version Negotiation and Protocol Bindings

## Purpose

A2A v1.0 defines a stable agent-to-agent interoperability model with explicit protocol-version and interface declarations. Clients should negotiate against what an Agent Card actually advertises instead of assuming that every remote agent supports the same transport, binding, or protocol revision.

## Version handling

Treat the advertised A2A protocol version as part of compatibility checks. A client should reject or downgrade safely when the remote version is outside its supported range rather than silently interpreting unknown fields or semantics as if they belonged to a familiar version.

## Supported interfaces

Agent Cards can advertise supported interfaces and transports in preference order. A robust client should:

1. select an interface it actually implements;
2. preserve the remote agent's declared protocol requirements;
3. avoid inventing fallbacks that were not advertised;
4. keep authentication and authorization policy bound to the selected interface; and
5. surface a clear compatibility error when no mutually supported interface exists.

## Extension handling

A2A extensions add functionality beyond the core protocol. Extension identifiers should be treated as explicit capabilities. Clients should send or consume an extension only when both sides understand its semantics and local policy allows it.

Unknown extensions should not become implicit authorization to perform extra actions. Prefer fail-closed behavior for security-sensitive extensions and preserve backward-compatible behavior only where the specification permits it.

## Operational guidance

- Record the negotiated version and interface in traces for debugging.
- Test mixed-version deployments before upgrading fleets.
- Keep parsers tolerant of permitted additive metadata but strict about security-critical semantics.
- Bind credentials to the actual endpoint and transport selected after negotiation.
- Re-read an Agent Card when cached compatibility data may be stale.

## Sources

- A2A Protocol — v1.0 documentation: https://a2a-protocol.org/v1.0.0/
- A2A Protocol — current specification repository: https://github.com/a2aproject/A2A/blob/main/docs/specification.md
- A2A Protocol — v1.0 release announcement: https://a2a-protocol.org/dev/blog/2026/03/12/a2a-protocol-ships-v10-production-ready-standard-for-agent-to-agent-communication/

## Scope note

This article focuses on interoperability behavior. Application-level task semantics and business authorization remain separate concerns.

# A2A Extension Negotiation

## Purpose

A2A extensions add functionality beyond the baseline protocol while preserving interoperability with extension-unaware clients. Extensions are inactive by default and are activated through explicit negotiation for a request.

## Activation

A client requests extensions using the `A2A-Extensions` HTTP header with extension URIs. The agent identifies the requested extensions it supports and activates only compatible ones. A client is responsible for activating any required dependencies declared by an extension specification.

## Versioning and compatibility

Use the extension URI as the primary identity and version signal. A breaking extension change should use a new URI. If a client asks for an unsupported version, the agent should not silently substitute a different version.

## Practical guidance

1. Discover declared extension support before depending on optional behavior.
2. Activate only extensions understood by both client and agent.
3. Resolve required dependencies explicitly.
4. Do not treat extension negotiation as authorization; validate permissions separately.
5. Ignore or reject unsupported security-sensitive extensions rather than guessing semantics.
6. Use distinct URIs for breaking extension revisions.
7. Test the baseline path with all optional extensions disabled.

## Sources

- A2A Protocol — Extensions: https://a2a-protocol.org/dev/topics/extensions/
- A2A Protocol — What's New in v1.0: https://a2a-protocol.org/latest/whats-new-v1/

## Scope note

Extension activation establishes compatible protocol behavior. Application authorization, trust policy, and business permissions remain separate controls.

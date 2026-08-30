# MCP Extensions Framework

## Purpose

The 2026-07-28 MCP revision formalized extensions as a first-class mechanism for capabilities that should evolve independently from the core protocol. Extensions allow clients and servers to opt into additional behavior without forcing every implementation to adopt it.

## Core model

MCP extensions use reverse-DNS-style identifiers and are negotiated through extension capability metadata. Official extensions live on their own lifecycle and may version independently from the core MCP specification.

The framework provides a path for features to mature outside the core protocol. The 2026 release includes official extensions such as Tasks, MCP Apps, and Enterprise-Managed Authorization.

## Practical controls

1. Treat every extension as opt-in unless both peers explicitly support it.
2. Use the exact registered extension identifier and version semantics defined by the extension.
3. Keep extension-specific state and errors separated from unrelated core-protocol assumptions.
4. Fail safely when a peer does not support an extension; do not silently reinterpret extension behavior as core behavior.
5. Track extension versions independently from the MCP core protocol version where the extension specification requires it.
6. Review extension security and privacy implications separately from core MCP transport security.
7. Avoid proprietary look-alike identifiers that could be confused with official extension namespaces.
8. Test downgrade and mixed-version behavior so an unsupported extension does not create authorization or data-integrity gaps.

## Evolution model

The formal extensions track lets capabilities move from experimental work toward official status without repeatedly destabilizing the base protocol. This complements MCP's feature lifecycle and deprecation policy.

## Sources

- Model Context Protocol — 2026-07-28 specification release: https://blog.modelcontextprotocol.io/posts/2026-07-28/
- Model Context Protocol — 2026-07-28 release candidate, Extensions Become First-Class: https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/

## Scope note

An extension being official does not mean every MCP client, server, or SDK supports it. Capability detection and compatibility checks remain necessary.

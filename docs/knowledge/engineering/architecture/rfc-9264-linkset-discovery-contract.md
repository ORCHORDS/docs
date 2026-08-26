# RFC 9264 Linkset Discovery Contract

**Issue:** Large or third-party web-link collections become inconsistent when squeezed into headers or copied into multiple representations without a canonical standalone contract.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Expose standalone links as application/linkset or application/linkset+json and advertise them with the linkset relation.
- Define link context explicitly so documents remain meaningful outside the original HTTP exchange.
- Use profile URIs to identify additional constraints without changing base Linkset semantics.
- Version relation, attribute, and profile rules and validate UTF-8 JSON representation.

## Verification

- Round-trip link contexts, targets, repeated hreflang values, and extension attributes.
- Discover the Linkset from a resource and validate its media type and profile.
- Test relative references after moving or caching the standalone document.

## Gotchas

- application/linkset differs from CoRE application/link-format.
- Multiple profile URIs must not impose conflicting constraints.

## Official sources

- https://www.rfc-editor.org/rfc/rfc9264.html

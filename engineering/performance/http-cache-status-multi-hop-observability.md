# HTTP Cache-Status Multi-Hop Observability

**Issue:** Proprietary cache headers make hit/miss and forwarding behavior incomparable across CDN and reverse-proxy layers, while exposing internal details indiscriminately creates reconnaissance risk.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Use RFC 9211 `Cache-Status` as a structured list when the cache stack supports it. Preserve prior members so order represents caches from origin-nearest to user-nearest. Emit only parameters needed for diagnosis—such as hit/forwarded/TTL/key detail—and define stable cache identifiers that reveal no hostnames, tenant IDs, topology, or secrets.

Parse with an HTTP Structured Fields implementation, not comma splitting. Sample or gate detailed fields in production and correlate them with request IDs and server-side cache metrics. Treat the header as explanatory telemetry, not proof that content was fresh or policy-compliant.

## Verification

Test hit, stale hit, revalidation, miss, bypass, collapsed request, local intermediary-generated errors, multiple cache hops, quoted/escaped detail, header truncation, CDN stripping, and privacy redaction. Compare the parsed chain to controlled cache logs and ensure user-visible responses never expose sensitive cache keys.

## Gotchas

Each cache decides when to emit the field, so absence is not a miss. An intermediary-generated response not based on stored content should not claim cached handling. Proprietary headers may coexist during migration. High-cardinality detail can inflate responses and telemetry cost.

## Sources

- [IETF RFC 9211 — Cache-Status HTTP Response Header](https://datatracker.ietf.org/doc/html/rfc9211)
- [IETF RFC 8941 — Structured Field Values for HTTP](https://datatracker.ietf.org/doc/html/rfc8941)

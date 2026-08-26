# Apply RFC 9213 Targeted Cache-Control by Layer

**Issue:** One Cache-Control policy cannot always express different requirements for a CDN and a downstream private cache. Targeted fields add precision but only for caches that recognize them.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls
- Define the target token and responsible cache layer explicitly.
- Send a safe general Cache-Control fallback for caches that ignore the targeted field.
- Apply targeted directives only at the addressed cache and forward other targets unchanged.
- Include targeted-field behavior in cache-key, invalidation, and privacy review.
- Observe actual Age/Cache-Status behavior at every layer.

## Verification
- Test aware and unaware caches, multiple targets, malformed fields, revalidation, private data, and invalidation.
- Remove a targeted field and confirm fallback remains safe.
- Trace object residence and reuse at each hop.

## Gotchas
A targeted field is not automatically understood by a product because its token resembles a vendor name. It supplements rather than erases general cache semantics.

## Official sources
- [RFC 9213](https://www.rfc-editor.org/rfc/rfc9213.html)
